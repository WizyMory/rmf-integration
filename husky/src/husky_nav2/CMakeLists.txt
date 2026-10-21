cmake_minimum_required(VERSION 3.8)
project(husky_nav2)

find_package(ament_cmake REQUIRED)
install(DIRECTORY config launch maps DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/wheel_tf_relay.py DESTINATION lib/${PROJECT_NAME})
install(FILES README.md DESTINATION share/${PROJECT_NAME})
ament_package()
