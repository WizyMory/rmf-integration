from pathlib import Path
from setuptools import find_packages, setup

name = 'brin_husky_hardware'
setup(
    name=name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + name]),
        ('share/' + name, ['package.xml', 'README.md']),
        ('share/' + name + '/launch', [str(p) for p in Path('launch').glob('*.py')]),
        ('share/' + name + '/config', [str(p) for p in Path('config').glob('*.yaml')]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='BRIN integration maintainers',
    maintainer_email='maintainer@example.com',
    description='Physical Husky A200 bridge, preflight and RMF launch',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={'console_scripts': [
        'tf_bridge = brin_husky_hardware.bridge:main',
        'preflight = brin_husky_hardware.preflight:main',
        'fleet_adapter = brin_husky_hardware.adapter:main',
        'send_task = brin_husky_hardware.send_task:main',
    ]},
)
