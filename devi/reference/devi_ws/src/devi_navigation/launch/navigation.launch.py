"""Layer 2 - Nav2 (navigasi otonom) DEVI.

Okt 2026: node Nav2 diinstansiasi langsung (sama dengan isi
nav2_bringup/launch/navigation_launch.py humble), bukan include file itu.
Alasannya rantai cmd_vel: versi lama memakai SetRemap('/cmd_vel' ->
'/devi/cmd_vel_nav'), yang ikut mengenai node lain sehingga controller_server
langsung ke twist_mux dan velocity_smoother terlewati. Di sini eksplisit:

    controller_server, behavior_server --cmd_vel--> /devi/cmd_vel_nav_raw
    velocity_smoother: /devi/cmd_vel_nav_raw -> /devi/cmd_vel_nav (input 'nav' twist_mux)

twist_mux (devi_bringup/config/twist_mux.yaml): joystick prioritas 100 > nav 10.
Tahan LB (dead man) dengan stik di tengah -> robot berhenti (perintah nol dari
joystick menang atas Nav2).

Butuh map -> odom (amcl atau slam_toolbox), odom -> base_link (ekf_local),
/map, dan /devi/rplidar/scan_filtered. Biasanya lewat bringup:

    ros2 launch devi_bringup bringup.launch.py              # amcl + navigasi
    ros2 launch devi_navigation navigation.launch.py        # sendiri (bringup navigation:=false)

Goal: RViz "2D Goal Pose" (Fixed Frame map) -> /goal_pose.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

CMD_VEL_RAW = '/devi/cmd_vel_nav_raw'
CMD_VEL_OUT = '/devi/cmd_vel_nav'   # WAJIB sama dengan topic 'nav' di twist_mux.yaml

LIFECYCLE_NODES = ['controller_server', 'smoother_server', 'planner_server',
                   'behavior_server', 'bt_navigator', 'waypoint_follower',
                   'velocity_smoother']


def generate_launch_description():
    config_dir = os.path.join(get_package_share_directory('devi_navigation'), 'config')
    # Nama argumen unik (30 Okt 2026): launch configuration berlaku global di satu
    # `ros2 launch`. Dulu 'params_file' -- sama dengan amcl.launch.py, sehingga di
    # bringup Nav2 ikut memakai amcl.yaml (tanpa parameter Nav2 -> 'No critics
    # defined for FollowPath').
    params_file = LaunchConfiguration('nav2_params_file')

    def nav2_node(package, executable, remappings=()):
        return Node(package=package, executable=executable, name=executable,
                    output='screen', parameters=[params_file],
                    remappings=list(remappings))

    return LaunchDescription([
        DeclareLaunchArgument(
            'nav2_params_file',
            default_value=os.path.join(config_dir, 'nav2_indoor.yaml'),
            description='File parameter Nav2 (indoor: nav2_indoor.yaml).'),

        nav2_node('nav2_controller', 'controller_server', [('cmd_vel', CMD_VEL_RAW)]),
        nav2_node('nav2_smoother', 'smoother_server'),
        nav2_node('nav2_planner', 'planner_server'),
        nav2_node('nav2_behaviors', 'behavior_server', [('cmd_vel', CMD_VEL_RAW)]),
        nav2_node('nav2_bt_navigator', 'bt_navigator'),
        nav2_node('nav2_waypoint_follower', 'waypoint_follower'),
        nav2_node('nav2_velocity_smoother', 'velocity_smoother',
                  [('cmd_vel', CMD_VEL_RAW), ('cmd_vel_smoothed', CMD_VEL_OUT)]),

        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_navigation',
            output='screen',
            parameters=[{'use_sim_time': False,
                         'autostart': True,
                         'node_names': LIFECYCLE_NODES}],
        ),
    ])