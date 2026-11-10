cmake_minimum_required(VERSION 3.8)
project(brin_rmf_maps)
find_package(ament_cmake REQUIRED)

# The server uses the same authoritative assets as the laptop. It does not
# need the simulator collision plugin or a Gazebo development installation.
set(BRIN_MAP_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../../../laptop/src/brin_rmf_maps")
foreach(asset maps nav_graphs worlds models tools)
  install(DIRECTORY "${BRIN_MAP_SOURCE}/${asset}" DESTINATION share/${PROJECT_NAME})
endforeach()
ament_package()
