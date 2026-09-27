"""Run physical MTMs/GooVis and Meta OpenXR against one PyBullet patient cart."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


PACKAGE_NAME = "dvrk_config_iros26"


def generate_launch_description():
    package_share = Path(get_package_share_directory(PACKAGE_NAME))
    pybullet_share = Path(get_package_share_directory("dvrk_pybullet"))

    simulator = ExecuteProcess(
        cmd=[
            LaunchConfiguration("pybullet_python"),
            str(pybullet_share / "scripts" / "simulator.py"),
            "--config", LaunchConfiguration("pybullet_config"),
            "--scene", "ECM_PSM1_PSM2_PSM3.yaml",
            "--scene", LaunchConfiguration("exercise"),
            "--gui", LaunchConfiguration("gui"),
        ],
        output="screen",
    )
    console_overlay = Node(
        package="dvrk_console",
        executable="stereo_display",
        name="stereo_display_console",
        output="screen",
        arguments=[
            "-c", str(package_share / "stereo_display_simulator_console.json")
        ],
    )
    meta_overlay = Node(
        package="dvrk_console",
        executable="stereo_display",
        name="stereo_display_meta",
        output="screen",
        arguments=[
            "-c", str(package_share / "stereo_display_simulator_meta.json")
        ],
    )
    dvrk_system = Node(
        package="dvrk_robot",
        executable="dvrk_system",
        name="dvrk_system",
        output="screen",
        cwd=str(package_share),
        arguments=[
            "--json-config",
            str(package_share / "system-MTML-MTMR-OpenXR-patient-cart-ROS.json"),
        ],
    )
    console_control_panel = Node(
        package="dvrk_console",
        executable="control_panel",
        name="control_panel_console",
        output="screen",
        arguments=[
            "--config", str(package_share / "control_panel_console.json")
        ],
    )
    meta_control_panel = Node(
        package="dvrk_console",
        executable="control_panel",
        name="control_panel_meta",
        output="screen",
        arguments=[
            "--config", str(package_share / "control_panel_Meta.json")
        ],
    )
    start_system = Node(
        package="dvrk_simulator_base",
        executable="start_dvrk_system",
        name="start_dvrk_system",
        output="screen",
        arguments=["--console", "console"],
    )
    rqt_monitor = ExecuteProcess(
        cmd=["rqt"],
        additional_env={
            "DVRK_RQT_ARMS": "ECM,PSM1,PSM2,PSM3",
            "DVRK_RQT_CONSOLE": LaunchConfiguration("rqt_console"),
        },
        condition=IfCondition(LaunchConfiguration("rqt")),
        output="screen",
    )

    stop_handlers = [
        RegisterEventHandler(
            OnProcessExit(
                target_action=action,
                on_exit=[EmitEvent(event=Shutdown(reason=reason))],
            )
        )
        for action, reason in (
            (simulator, "PyBullet simulator exited"),
            (dvrk_system, "dvrk_system exited"),
            (console_overlay, "console stereo overlay exited"),
            (meta_overlay, "Meta stereo overlay exited"),
        )
    ]

    return LaunchDescription([
        DeclareLaunchArgument(
            "exercise",
            default_value="tray_cubes.yaml",
            description="Exercise scene YAML path or installed exercise filename.",
        ),
        DeclareLaunchArgument(
            "gui",
            default_value="false",
            description="Show the local PyBullet debug GUI.",
        ),
        DeclareLaunchArgument(
            "rqt",
            default_value="false",
            description="Start rqt for arm and console monitoring.",
        ),
        DeclareLaunchArgument(
            "rqt_console",
            default_value="console",
            description="Console namespace shown by rqt: console or Meta.",
        ),
        DeclareLaunchArgument(
            "pybullet_config",
            default_value=str(package_share / "pybullet_patient_cart.yaml"),
            description="PyBullet runtime YAML configuration.",
        ),
        DeclareLaunchArgument(
            "pybullet_python",
            default_value=str(Path.home() / "devel" / "venv-pybullet" / "bin" / "python3"),
            description="Python interpreter with PyBullet requirements installed.",
        ),
        simulator,
        console_overlay,
        meta_overlay,
        dvrk_system,
        console_control_panel,
        meta_control_panel,
        start_system,
        rqt_monitor,
        *stop_handlers,
    ])
