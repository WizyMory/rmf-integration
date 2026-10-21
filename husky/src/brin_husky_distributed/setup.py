from pathlib import Path
from setuptools import find_packages, setup


name = 'brin_husky_distributed'
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
    description='Physical Husky laptop/robot split with profile matching',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={'console_scripts': [
        'profile_announcer = brin_husky_distributed.announcer:main',
    ]},
)
