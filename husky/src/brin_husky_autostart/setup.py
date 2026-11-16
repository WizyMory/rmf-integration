from setuptools import find_packages, setup

setup(name='brin_husky_autostart', version='0.1.0', packages=find_packages(exclude=['test']),
      data_files=[('share/ament_index/resource_index/packages', ['resource/brin_husky_autostart']),
                  ('share/brin_husky_autostart', ['package.xml']),
                  ('share/brin_husky_autostart/config', ['config/bringup.yaml'])],
      install_requires=['setuptools'], zip_safe=True,
      maintainer='BRIN integration maintainers', maintainer_email='maintainer@example.com',
      description='Ordered Husky boot bringup', license='Apache-2.0',
      tests_require=['pytest'], entry_points={'console_scripts': [
          'bringup_supervisor = brin_husky_autostart.supervisor:main']})
