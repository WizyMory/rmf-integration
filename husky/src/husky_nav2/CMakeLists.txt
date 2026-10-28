cmake_minimum_required(VERSION 3.8)
project(husky_nav2)

find_package(ament_cmake REQUIRED)
install(DIRECTORY config launch maps DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/wheel_tf_relay.py scripts/rmf_graph_markers.py
  DESTINATION lib/${PROJECT_NAME})
install(FILES README.md DESTINATION share/${PROJECT_NAME})
if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(rmf_visualization test/test_rmf_visualization.py)
endif()
ament_package()
