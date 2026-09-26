"""Start the MTMR/PSM2 dVRK system with the OAK stereo display stack."""

from pathlib import Path

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessIO
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


PACKAGE_NAME = "dvrk_config_iros26"


def generate_launch_description():
    package_share = Path(get_package_share_directory(PACKAGE_NAME))
    package_prefix = Path(get_package_prefix(PACKAGE_NAME))
    system_config = package_share / "system-MTMR-PSM2-OAK.json"
    alignment_config = package_share / "stereo_alignment_oak.json"
    display_config = package_share / "stereo_display_oak.json"
    # preview_oak.py is installed under the package's lib dir, not its share dir
    preview_script = package_prefix / "lib" / PACKAGE_NAME / "preview_oak.py"

    dvrk_system = Node(
        package="dvrk_robot",
        executable="dvrk_system",
        name="dvrk_system",
        output="screen",
        cwd=str(package_share),
        arguments=["--json-config", str(system_config)],
    )

    preview_oak = ExecuteProcess(
        cmd=[
            LaunchConfiguration("oak_python"),
            "-u",
            str(preview_script),
            "--mode", LaunchConfiguration("oak_mode"),
            "--preview", "false",
            "--gstsocket", "true",
        ],
        output="screen",
    )

    stereo_alignment = Node(
        package="dvrk_data",
        executable="stereo_alignment",
        name="stereo_alignment",
        output="screen",
        arguments=["-c", str(alignment_config)],
    )

    stereo_display = Node(
        package="dvrk_console",
        executable="stereo_display",
        name="stereo_display",
        output="screen",
        arguments=["-c", str(display_config)],
    )

    control_panel = Node(
        package="dvrk_console",
        executable="control_panel",
        name="control_panel",
        output="screen",
    )

    # stereo_alignment's unixfdsrc must connect to preview_oak's unixfdsink sockets,
    # which only exist once the OAK GStreamer pipeline is playing. Starting
    # stereo_alignment too early causes a silent/failed connection, so defer it
    # until preview_oak reports the pipeline is up.
    started = {"stereo_alignment": False, "stereo_display": False}

    def on_preview_oak_output(event):
        if started["stereo_alignment"]:
            return None
        text = event.text.decode(errors="replace")
        if "Pipeline started successfully" in text:
            started["stereo_alignment"] = True
            return [stereo_alignment]
        return None

    start_stereo_alignment = RegisterEventHandler(
        OnProcessIO(
            target_action=preview_oak,
            on_stdout=on_preview_oak_output,
            on_stderr=on_preview_oak_output,
        )
    )

    # Likewise, stereo_display connects to stereo_alignment's unixfdsink output,
    # so it must not start until that background pipeline is confirmed running.
    def on_stereo_alignment_output(event):
        if started["stereo_display"]:
            return None
        text = event.text.decode(errors="replace")
        if "Stereo alignment background pipeline started" in text:
            started["stereo_display"] = True
            return [stereo_display]
        return None

    start_stereo_display = RegisterEventHandler(
        OnProcessIO(
            target_action=stereo_alignment,
            on_stdout=on_stereo_alignment_output,
            on_stderr=on_stereo_alignment_output,
        )
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "oak_mode",
            default_value="a",
            description="OAK camera mode preset passed to preview_oak.py (a-e).",
        ),
        DeclareLaunchArgument(
            "oak_python",
            default_value=str(Path.home() / "devel" / "venv-oak" / "bin" / "python3"),
            description="Python executable (inside the OAK venv) used to run preview_oak.py.",
        ),
        dvrk_system,
        preview_oak,
        start_stereo_alignment,
        start_stereo_display,
        control_panel,
    ])
