from pathlib import Path
from setuptools import find_packages, setup

name = 'brin_devi_fleet_adapter'
setup(
    name=name, version='0.1.0', packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + name]),
        ('share/' + name, ['package.xml']),
        *[('share/' + name + '/' + directory,
           [str(p) for p in Path(directory).glob('*') if p.is_file()])
          for directory in ('config', 'launch', 'maps', 'nav_graphs')],
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='BRIN integration maintainers',
    maintainer_email='maintainer@example.com', license='Apache-2.0',
    description='Physical Devi Nav2 domain 73 to Open-RMF domain 0',
    entry_points={'console_scripts': [
        'fleet_adapter = brin_devi_fleet_adapter.adapter:main',
        'preflight = brin_devi_fleet_adapter.preflight:main',
        'profile_info = brin_devi_fleet_adapter.profiles:main',
        'link_check = brin_devi_fleet_adapter.link_check:main',
        'initial_pose_bridge = brin_devi_fleet_adapter.initial_pose_bridge:main',
        'adapter_supervisor = brin_devi_fleet_adapter.supervisor:main',
        'visualization_bridge = brin_devi_fleet_adapter.visualization_bridge:main',
    ]},
)
