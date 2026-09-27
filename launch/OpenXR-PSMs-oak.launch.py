"""Run physical PSM1/PSM2 from sawOpenXR with OAK stereo video."""

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
    system_config = package_share / "system-OpenXR-PSM1-PSM2-OAK.json"
    alignment_config = package_share / "stereo_alignment_oak.json"
    display_config = package_share / "stereo_display_openxr_oak.json"
    preview_script = package_prefix / "lib" / PACKAGE_NAME / "preview_oak.py"

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
        name="openxr_stereo_display",
        output="screen",
        arguments=["-c", str(display_config)],
    )
    dvrk_system = Node(
        package="dvrk_robot",
        executable="dvrk_system",
        name="dvrk_system",
        output="screen",
        cwd=str(package_share),
        arguments=["--json-config", str(system_config)],
    )
    control_panel = Node(
        package="dvrk_console",
        executable="control_panel",
        name="control_panel",
        output="screen",
    )
    start_system = Node(
        package="dvrk_simulator_base",
        executable="start_dvrk_system",
        name="start_dvrk_system",
        output="screen",
        arguments=["--console", LaunchConfiguration("console")],
    )

    started = {
        "stereo_alignment": False,
        "stereo_display": False,
        "dvrk_system": False,
    }

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

    def on_stereo_display_output(event):
        if started["dvrk_system"]:
            return None
        text = event.text.decode(errors="replace")
        if "Stereo display pipeline started" in text:
            started["dvrk_system"] = True
            return [dvrk_system, control_panel, start_system]
        return None

    launch_dvrk_system = RegisterEventHandler(
        OnProcessIO(
            target_action=stereo_display,
            on_stdout=on_stereo_display_output,
            on_stderr=on_stereo_display_output,
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
            description="Python executable inside the OAK virtual environment.",
        ),
        DeclareLaunchArgument(
            "console",
            default_value="console",
            description="dVRK console ROS namespace.",
        ),
        # Register handlers before preview_oak can emit readiness output.
        start_stereo_alignment,
        start_stereo_display,
        launch_dvrk_system,
        preview_oak,
    ])
