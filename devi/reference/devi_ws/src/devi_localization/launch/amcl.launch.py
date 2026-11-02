"""Lokalisasi di peta tersimpan: map_server + AMCL + ekf_local.

Sudah termasuk di bringup (Okt 2026, bawaan localization:=amcl):

    ros2 launch devi_bringup bringup.launch.py                          # peta workshop_l_1
    ros2 launch devi_bringup bringup.launch.py map:=/path/ke/peta.yaml

Untuk debugging sendiri, di atas bringup tanpa lokalisasi:

    ros2 launch devi_bringup bringup.launch.py localization:=none
    ros2 launch devi_localization amcl.launch.py

Isi launch ini:
- localization.launch.py dengan enable_global:=false -> hanya ekf_local
  (TF odom -> base_link). ekf_global sengaja TIDAK jalan: dia dan AMCL
  sama-sama publish map -> odom.
- map_server (config/amcl.yaml, peta dari argumen 'map') -> /map.
- amcl (config/amcl.yaml) -> TF map -> odom, /amcl_pose, /particle_cloud.
- lifecycle_manager_localization: configure + activate map_server dan amcl.

JANGAN dijalankan bersamaan mapping.launch.py: slam_toolbox juga publish /map
dan map -> odom.

Pose awal: RViz (Fixed Frame map) -> "2D Pose Estimate", klik posisi robot
di peta lalu tarik ke arah hadapnya. Lalu jalankan robot sedikit supaya
partikel mengumpul (AMCL baru update setelah bergerak 0.25 m atau 0.2 rad).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory('devi_localization')
    maps_dir = os.path.join(get_package_share_directory('devi_navigation'), 'maps')

    map_yaml = LaunchConfiguration('map')
    # Nama unik: lihat catatan di devi_navigation/launch/navigation.launch.py.
    params_file = LaunchConfiguration('amcl_params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'map',
            default_value=os.path.join(maps_dir, 'workshop_l_1.yaml'),
            description='File .yaml peta (hasil map_saver_cli).'),
        DeclareLaunchArgument(
            'amcl_params_file',
            default_value=os.path.join(share, 'config', 'amcl.yaml'),
            description='File parameter map_server + amcl.'),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'localization.launch.py')),
            launch_arguments={'enable_global': 'false'}.items(),
        ),

        Node(
            package='nav2_map_server',
            executable='map_server',
            name='map_server',
            output='screen',
            parameters=[params_file, {'yaml_filename': map_yaml}],
        ),
        Node(
            package='nav2_amcl',
            executable='amcl',
            name='amcl',
            output='screen',
            parameters=[params_file],
        ),
        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_localization',
            output='screen',
            parameters=[{'use_sim_time': False,
                         'autostart': True,
                         'node_names': ['map_server', 'amcl']}],
        ),
    ])