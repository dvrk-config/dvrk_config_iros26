cmake_minimum_required(VERSION 3.16)
project(dvrk_config_iros26 VERSION 0.1.0)

find_package(ament_cmake REQUIRED)

install(
  FILES
    MTML-22723.json
    MTMR-22403.json
    PSM2-27374.json
    gc-MTML-22723.json
    gc-MTMR-22403.json
    sawRobotIO1394-MTML-22723.json
    sawRobotIO1394-MTML-gripper-22723.json
    sawRobotIO1394-MTMR-22403.json
    sawRobotIO1394-MTMR-gripper-22403.json
    sawRobotIO1394-PSM2-27374.json
    stereo_alignment.json
    stereo_alignment_oak.json
    stereo_display.json
    stereo_display_oak.json
    stereo_display_simulator.json
    stereo_source.json
    newton_patient_cart.yaml
    pybullet_patient_cart.yaml
    system-MTML.json
    system-MTMR.json
    system-MTML-MTMR-patient-cart-ROS.json
    system-MTMR-PSM2-OAK.json
    system-PSM1.json
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS preview_oak.py
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
