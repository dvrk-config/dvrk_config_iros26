"""Run physical MTMs and pedals with the Newton virtual patient cart and HMD."""

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
    newton_share = Path(get_package_share_directory("dvrk_newton"))
    default_config = package_share / "newton_patient_cart.yaml"
    system_config = package_share / "system-MTML-MTMR-patient-cart-ROS.json"
    display_config = package_share / "stereo_display_simulator.json"

    simulator = ExecuteProcess(
        cmd=[
            LaunchConfiguration("newton_python"),
            str(newton_share / "scripts" / "simulator.py"),
            "--config", LaunchConfiguration("newton_config"),
            "--scene", "ECM_PSM1_PSM2_PSM3.yaml",
            "--scene", LaunchConfiguration("exercise"),
            "--headless", LaunchConfiguration("headless"),
        ],
        output="screen",
    )
    dvrk_system = Node(
        package="dvrk_robot",
        executable="dvrk_system",
        name="dvrk_system",
        output="screen",
        cwd=str(package_share),
        arguments=["--json-config", str(system_config)],
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
    start_system = Node(
        package="dvrk_simulator_base",
        executable="start_dvrk_system",
        output="screen",
        arguments=["--console", LaunchConfiguration("console")],
    )
    rqt_monitor = ExecuteProcess(
        cmd=["rqt"],
        additional_env={
            "DVRK_RQT_ARMS": "ECM,PSM1,PSM2,PSM3",
            "DVRK_RQT_CONSOLE": LaunchConfiguration("console"),
        },
        condition=IfCondition(LaunchConfiguration("rqt")),
        output="screen",
    )

    stop_with_simulator = RegisterEventHandler(
        OnProcessExit(
            target_action=simulator,
            on_exit=[EmitEvent(event=Shutdown(reason="NVIDIA Newton simulator exited"))],
        )
    )
    stop_with_system = RegisterEventHandler(
        OnProcessExit(
            target_action=dvrk_system,
            on_exit=[EmitEvent(event=Shutdown(reason="dvrk_system exited"))],
        )
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "exercise", default_value="tray_cubes.yaml",
            description="Exercise scene YAML path or installed exercise filename.",
        ),
        DeclareLaunchArgument(
            "headless", default_value="true",
            description="Run Newton without its desktop viewer window.",
        ),
        DeclareLaunchArgument(
            "console", default_value="console",
            description="dVRK console ROS namespace.",
        ),
        DeclareLaunchArgument(
            "rqt", default_value="false",
            description="Start rqt for console and arm monitoring.",
        ),
        DeclareLaunchArgument(
            "newton_config", default_value=str(default_config),
            description="Newton runtime YAML configuration.",
        ),
        DeclareLaunchArgument(
            "newton_python",
            default_value=str(Path.home() / "devel" / "venv-newton" / "bin" / "python3"),
            description="Python interpreter with Newton requirements installed.",
        ),
        simulator,
        stereo_display,
        control_panel,
        dvrk_system,
        start_system,
        rqt_monitor,
        stop_with_simulator,
        stop_with_system,
    ])
