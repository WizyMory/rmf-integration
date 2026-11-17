from glob import glob
from setuptools import find_packages, setup

setup(
    name='rmf_nav2_onboard', version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[('share/ament_index/resource_index/packages', ['resource/rmf_nav2_onboard']),
                ('share/rmf_nav2_onboard', ['package.xml']),
                ('share/rmf_nav2_onboard/launch', glob('launch/*.launch.py'))],
    package_data={'rmf_nav2_onboard': ['templates/*.yaml']},
    install_requires=['setuptools', 'PyYAML'], zip_safe=True,
    maintainer='RMF integration maintainers', maintainer_email='maintainer@example.com',
    description='Modular physical Nav2 to Open-RMF integration', license='Apache-2.0',
    entry_points={'console_scripts': ['robot = rmf_nav2_onboard.cli:main',
                                      'site_profile = rmf_nav2_onboard.cli:profile_main']},
)
