#!/usr/bin/env python3
"""
Preview side-by-side stereo stream from an OAK USB camera using DepthAI and GStreamer glimagesink.
"""

import argparse
import signal
import sys
import threading
import time

import cv2
import depthai as dai
import numpy as np

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst


# Map human-friendly socket names to dai.CameraBoardSocket
SOCKET_MAP = {
    "A": dai.CameraBoardSocket.CAM_A,
    "CAM_A": dai.CameraBoardSocket.CAM_A,
    "RGB": dai.CameraBoardSocket.CAM_A,
    "B": dai.CameraBoardSocket.CAM_B,
    "CAM_B": dai.CameraBoardSocket.CAM_B,
    "LEFT": dai.CameraBoardSocket.CAM_B,
    "C": dai.CameraBoardSocket.CAM_C,
    "CAM_C": dai.CameraBoardSocket.CAM_C,
    "RIGHT": dai.CameraBoardSocket.CAM_C,
    "D": dai.CameraBoardSocket.CAM_D,
    "CAM_D": dai.CameraBoardSocket.CAM_D,
}


def parse_socket(sock_str: str) -> dai.CameraBoardSocket:
    key = sock_str.strip().upper()
    if key in SOCKET_MAP:
        return SOCKET_MAP[key]
    raise ValueError(f"Unknown camera socket: '{sock_str}'. Supported: {list(SOCKET_MAP.keys())}")


def detect_camera_sockets(device: dai.Device, requested_left: str | None, requested_right: str | None):
    connected = device.getConnectedCameras()
    print(f"[OAK] Connected camera sockets: {[c.name for c in connected]}")

    sensor_names = device.getCameraSensorNames()
    for sock, name in sensor_names.items():
        print(f"  - {sock.name}: {name}")

    if requested_left:
        left_sock = parse_socket(requested_left)
    else:
        # Default heuristics: CAM_B if present, else first connected camera
        if dai.CameraBoardSocket.CAM_B in connected:
            left_sock = dai.CameraBoardSocket.CAM_B
        elif dai.CameraBoardSocket.CAM_A in connected:
            left_sock = dai.CameraBoardSocket.CAM_A
        elif connected:
            left_sock = connected[0]
        else:
            raise RuntimeError("No cameras detected on OAK device!")

    if requested_right:
        right_sock = parse_socket(requested_right)
    else:
        # Default heuristics: CAM_C if present, else CAM_B if left is CAM_A, else second camera
        if left_sock == dai.CameraBoardSocket.CAM_B and dai.CameraBoardSocket.CAM_C in connected:
            right_sock = dai.CameraBoardSocket.CAM_C
        elif left_sock == dai.CameraBoardSocket.CAM_A and dai.CameraBoardSocket.CAM_B in connected:
            right_sock = dai.CameraBoardSocket.CAM_B
        elif len(connected) > 1:
            right_sock = [c for c in connected if c != left_sock][0]
        else:
            right_sock = left_sock

    if left_sock not in connected:
        print(f"[WARNING] Left socket {left_sock.name} is not in connected cameras: {[c.name for c in connected]}")
    if right_sock not in connected:
        print(f"[WARNING] Right socket {right_sock.name} is not in connected cameras: {[c.name for c in connected]}")

    print(f"[OAK] Using Left: {left_sock.name}, Right: {right_sock.name}")
    return left_sock, right_sock


def build_gst_pipeline(width: int, height: int, fps: int, sink: str = "glimagesink"):
    pipeline_str = (
        f"appsrc name=src is-live=true do-timestamp=true format=time max-buffers=1 leaky-type=downstream "
        f"caps=video/x-raw,format=BGR,width={width},height={height},framerate={fps}/1 ! "
        f"videoconvert ! {sink} sync=false"
    )
    print(f"[GStreamer] Pipeline: {pipeline_str}")
    pipeline = Gst.parse_launch(pipeline_str)
    if not pipeline:
        raise RuntimeError("Failed to parse GStreamer pipeline")
    appsrc = pipeline.get_by_name("src")
    return pipeline, appsrc


class OakPreviewApp:
    def __init__(self, left_sock: dai.CameraBoardSocket, right_sock: dai.CameraBoardSocket,
                 width: int = 1280, height: int = 800, fps: int = 15, sink: str = "glimagesink"):
        self.left_sock = left_sock
        self.right_sock = right_sock
        self.width = width
        self.height = height
        self.fps = fps
        self.sink = sink
        self.sbs_width = width * 2
        self.sbs_height = height

        self.running = False
        self.loop = GLib.MainLoop()
        self.gst_pipeline, self.appsrc = build_gst_pipeline(self.sbs_width, self.sbs_height, self.fps, self.sink)

        # Bus watch
        bus = self.gst_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_gst_message)

    def on_gst_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("[GStreamer] End of stream")
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"[GStreamer Error]: {err.message}")
            if debug:
                print(f"[GStreamer Debug]: {debug}")
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        print("\n[App] Stopping...")
        if self.gst_pipeline:
            self.gst_pipeline.set_state(Gst.State.NULL)
        if self.loop.is_running():
            self.loop.quit()

    def run(self):
        # Create DepthAI Pipeline
        with dai.Pipeline(dai.Device()) as dai_pipeline:
            device = dai_pipeline.getDefaultDevice()
            usb_speed = device.getUsbSpeed()
            print(f"[OAK] Device USB connection speed: {usb_speed.name}")
            if usb_speed != dai.UsbSpeed.SUPER:
                print("[NOTE] Camera is connected via USB 2.0 (HIGH speed).")
                print("       For full 30+ FPS at 1280x800 with minimum latency,")
                print("       plug into a blue USB 3.0 port with a USB 3.0 cable.")

            # Left camera node
            cam_l = dai_pipeline.create(dai.node.Camera)
            cam_l.setSensorType(dai.CameraSensorType.COLOR)
            cam_l.build(self.left_sock, sensorFps=self.fps)
            cap_l = dai.ImgFrameCapability()
            cap_l.size.fixed((self.width, self.height))
            cap_l.fps.fixed(self.fps)
            out_l = cam_l.requestOutput(cap_l, True)
            q_l = out_l.createOutputQueue(maxSize=1, blocking=False)

            # Right camera node
            cam_r = dai_pipeline.create(dai.node.Camera)
            cam_r.setSensorType(dai.CameraSensorType.COLOR)
            cam_r.build(self.right_sock, sensorFps=self.fps)
            cap_r = dai.ImgFrameCapability()
            cap_r.size.fixed((self.width, self.height))
            cap_r.fps.fixed(self.fps)
            out_r = cam_r.requestOutput(cap_r, True)
            q_r = out_r.createOutputQueue(maxSize=1, blocking=False)

            dai_pipeline.start()
            print("[OAK] Pipeline started successfully")

            # Start GStreamer
            self.gst_pipeline.set_state(Gst.State.PLAYING)
            self.running = True

            def get_latest_frame(q):
                """Drains any buffered queue backlog so we always display the freshest frame."""
                frame = q.get()
                while True:
                    f = q.tryGet()
                    if f is None:
                        return frame
                    frame = f

            def capture_thread_func():
                fps_time = time.monotonic()
                fps_count = 0

                while self.running:
                    frame_l = get_latest_frame(q_l)
                    frame_r = get_latest_frame(q_r)
                    if frame_l is None or frame_r is None:
                        time.sleep(0.001)
                        continue

                    # Measure capture-to-host delivery latency
                    now_mono = time.monotonic()
                    frame_ts = frame_l.getTimestamp().total_seconds()
                    delivery_latency_ms = (now_mono - frame_ts) * 1000.0

                    img_l = frame_l.getCvFrame()
                    img_r = frame_r.getCvFrame()

                    # Combine horizontally: Left on left, Right on right
                    sbs = np.hstack((img_l, img_r))
                    data = sbs.tobytes()

                    buf = Gst.Buffer.new_wrapped(data)
                    # GStreamer do-timestamp=true assigns the pipeline clock; no manual PTS needed
                    buf.pts = Gst.CLOCK_TIME_NONE
                    buf.dts = Gst.CLOCK_TIME_NONE

                    ret = self.appsrc.emit("push-buffer", buf)
                    if ret != Gst.FlowReturn.OK:
                        print(f"[GStreamer] push-buffer returned {ret}")
                        break

                    fps_count += 1
                    now = time.monotonic()
                    if now - fps_time >= 1.0:
                        measured_fps = fps_count / (now - fps_time)
                        print(f"\r[Preview] Streaming ({self.sbs_width}x{self.sbs_height}) @ {measured_fps:.1f} FPS | Capture-to-host: {delivery_latency_ms:.1f} ms   ", end="", flush=True)
                        fps_count = 0
                        fps_time = now

                self.stop()

            worker = threading.Thread(target=capture_thread_func, daemon=True)
            worker.start()

            # Run GLib main loop for GStreamer window
            try:
                self.loop.run()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
                worker.join(timeout=1.0)


PRESET_MODES = {
    "a": {"width": 640, "height": 400, "fps": 30, "desc": "640x400 @ 30 FPS  (Native 16:10, max smooth framerate over USB 2.0)"},
    "b": {"width": 720, "height": 480, "fps": 30, "desc": "720x480 @ 30 FPS  (NTSC/WVGA, max pixel count at 30 FPS on USB 2.0)"},
    "c": {"width": 1280, "height": 800, "fps": 12, "desc": "1280x800 @ 12 FPS (Full sensor resolution at max stable USB 2.0 speed)"},
    "d": {"width": 1280, "height": 800, "fps": 10, "desc": "1280x800 @ 10 FPS (Full sensor resolution with generous USB bandwidth margin)"},
    "e": {"width": 1280, "height": 800, "fps": 30, "desc": "1280x800 @ 30 FPS (Full resolution & framerate; requires USB 3.0 port & cable)"},
}


def main():
    mode_help = "Predefined mode preset:\n" + "\n".join(
        f"  {k}: {v['desc']}" for k, v in PRESET_MODES.items()
    )

    parser = argparse.ArgumentParser(
        description="Preview OAK stereo camera in side-by-side using GStreamer",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-m", "--mode", type=str, default="a", choices=list(PRESET_MODES.keys()),
                        help=mode_help + "\n(default: a)")
    parser.add_argument("--cam-left", type=str, default=None,
                        help="Left camera socket (e.g. CAM_A, CAM_B, CAM_C). Auto-detects if omitted.")
    parser.add_argument("--cam-right", type=str, default=None,
                        help="Right camera socket (e.g. CAM_A, CAM_B, CAM_C). Auto-detects if omitted.")
    parser.add_argument("--width", type=int, default=None, help="Override width (defaults to selected --mode)")
    parser.add_argument("--height", type=int, default=None, help="Override height (defaults to selected --mode)")
    parser.add_argument("--fps", type=int, default=None, help="Override framerate (defaults to selected --mode)")
    parser.add_argument("--sink", type=str, default="glimagesink", help="GStreamer video sink (default: glimagesink)")

    args = parser.parse_args()

    mode_cfg = PRESET_MODES[args.mode.lower()]
    width = args.width if args.width is not None else mode_cfg["width"]
    height = args.height if args.height is not None else mode_cfg["height"]
    fps = args.fps if args.fps is not None else mode_cfg["fps"]

    print(f"[OAK] Selected Mode '{args.mode}': {width}x{height} @ {fps} FPS ({mode_cfg['desc']})")

    Gst.init(None)

    # Initial device scan for sockets
    devices = dai.Device.getAllAvailableDevices()
    if not devices:
        print("Error: No OAK devices found via DepthAI. Please ensure camera is plugged in.")
        sys.exit(1)

    with dai.Device() as test_dev:
        left_sock, right_sock = detect_camera_sockets(test_dev, args.cam_left, args.cam_right)

    app = OakPreviewApp(
        left_sock=left_sock,
        right_sock=right_sock,
        width=width,
        height=height,
        fps=fps,
        sink=args.sink,
    )

    def sig_handler(sig, frame):
        app.stop()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    app.run()


if __name__ == "__main__":
    main()
