from setuptools import setup, find_packages
from pathlib import Path
name = 'brin_husky_bringup'
data_files = [('share/ament_index/resource_index/packages', ['resource/'+name]), ('share/'+name, ['package.xml'])]
for folder in ('launch', 'config', 'rviz'):
    for directory in sorted({p.parent for p in Path(folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)}):
        data_files.append(('share/'+name+'/'+str(directory), [str(p) for p in directory.iterdir() if p.is_file()]))
setup(name=name, version='0.1.0', packages=find_packages(exclude=['test']),
      data_files=data_files, install_requires=['setuptools'], zip_safe=True,
      maintainer='BRIN integration maintainers', maintainer_email='maintainer@example.com',
      description='Two-Husky BRIN simulation integration', license='Apache-2.0',
      tests_require=['pytest'], entry_points={'console_scripts': ['wait_for_controllers = brin_husky_bringup.wait_for_controllers:main', 'serialized_spawner = brin_husky_bringup.serialized_spawner:main', 'prepare_robots = brin_husky_bringup.prepare:main', 'validate_runtime = brin_husky_bringup.validate_runtime:main', 'publish_documentation_markers = brin_husky_bringup.documentation_markers:main']})
