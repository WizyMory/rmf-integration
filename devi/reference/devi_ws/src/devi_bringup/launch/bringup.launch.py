"""Titik masuk penuh: robot_config -> sensors -> actuation -> localization -> navigation -> safety -> mission.

devi_bringup sekarang ORKESTRATOR MURNI (Juli 2026) -- localization dan
navigation dipindah ke package sendiri (devi_localization,
devi_navigation), konsisten dengan sensors/safety/mission/actuation yang
sudah lebih dulu punya launch+config sendiri. devi_bringup cuma
menyisakan robot_base.launch.py (teleop/twist_mux, genuinely
cross-cutting karena menggabungkan cmd_vel dari banyak sumber) dan
telemetry.launch.py.

Urutan include sengaja dipisah per file supaya tiap layer bisa dijalankan
sendiri-sendiri saat debugging:
    ros2 launch devi_sensor all_sensors.launch.py
    ros2 launch devi_localization localization.launch.py
    ros2 launch devi_navigation navigation.launch.py
    ros2 launch devi_safety safety.launch.py     (lewat devi_bringup/launch/safety.launch.py)
    ros2 launch devi_mission mission.launch.py

Lokalisasi indoor (Okt 2026) dipilih lewat argumen 'localization':
    ros2 launch devi_bringup bringup.launch.py                        # amcl, workshop_l_1
    ros2 launch devi_bringup bringup.launch.py map:=/path/peta.yaml   # amcl, peta lain
    ros2 launch devi_bringup bringup.launch.py localization:=mapping  # slam_toolbox
    ros2 launch devi_bringup bringup.launch.py localization:=none     # base + sensor saja
amcl dan mapping saling eksklusif (keduanya publish /map dan map -> odom).
Jangan jalankan amcl.launch.py / mapping.launch.py terpisah di atas bringup
yang sudah memuat salah satunya -- ganti argumen ini, atau pakai
localization:=none lalu jalankan launch-nya sendiri.

Navigasi otonom Nav2 (Okt 2026), argumen 'navigation' (bawaan true):
    ros2 launch devi_bringup bringup.launch.py navigation:=false      # tanpa Nav2

RViz (Okt 2026, rviz/devi.rviz), argumen 'rviz' (bawaan true):
    ros2 launch devi_bringup bringup.launch.py rviz:=false            # mis. lewat SSH tanpa layar
Menutup jendela RViz tidak mematikan node lain.
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition, LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    bringup_dir = get_package_share_directory('devi_bringup')
    mission_dir = get_package_share_directory('devi_mission')
    localization_dir = get_package_share_directory('devi_localization')
    navigation_dir = get_package_share_directory('devi_navigation')

    def include(name, base_dir, condition=None):
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(base_dir, 'launch', name)),
            condition=condition)

    return LaunchDescription([
        DeclareLaunchArgument(
            'localization', default_value='amcl', choices=['amcl', 'mapping', 'none'],
            description='amcl: lokalisasi di peta tersimpan; mapping: slam_toolbox; '
                        'none: tanpa lokalisasi.'),
        DeclareLaunchArgument(
            'navigation', default_value='true', choices=['true', 'false'],
            description='Nav2 (devi_navigation/navigation.launch.py, nav2_indoor.yaml).'),
        DeclareLaunchArgument(
            'rviz', default_value='true', choices=['true', 'false'],
            description='Buka RViz (rviz_config). false kalau tanpa layar (SSH).'),
        DeclareLaunchArgument(
            'rviz_config', default_value=os.path.join(bringup_dir, 'rviz', 'devi.rviz'),
            description='File config RViz.'),

        include('robot_base.launch.py', bringup_dir),
        include('sensors.launch.py', bringup_dir),
        # Okt 2026: lokalisasi indoor (RPLIDAR C1). Masing-masing sudah memuat
        # ekf_local. Argumen 'map' (amcl) diteruskan otomatis dari command line.
        include('amcl.launch.py', localization_dir,
                LaunchConfigurationEquals('localization', 'amcl')),
        include('mapping.launch.py', localization_dir,
                LaunchConfigurationEquals('localization', 'mapping')),
        # include('actuation.launch.py', bringup_dir),
        # Dual-EKF + GNSS outdoor (DELL-E); ekf_global bentrok dengan amcl/mapping.
        # include('localization.launch.py', localization_dir),
        # Okt 2026: Nav2 indoor. Butuh map -> odom dari amcl/mapping di atas.
        include('navigation.launch.py', navigation_dir,
                IfCondition(LaunchConfiguration('navigation'))),
        # Okt 2026: RViz. output='log' -- pesan GLSL rviz2 (peringatan shader Map,
        # tidak berbahaya) tidak ikut memenuhi terminal bringup.
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', LaunchConfiguration('rviz_config')],
            output='log',
            condition=IfCondition(LaunchConfiguration('rviz')),
        ),
        # include('safety.launch.py', bringup_dir),
        # include('telemetry.launch.py', bringup_dir),
        # include('mission.launch.py', mission_dir),
        # devi_perception belum diinclude di sini - node-nya belum
        # diimplementasikan (lihat entry_points kosong di setup.py),
        # tambahkan setelah node siap.
    ])