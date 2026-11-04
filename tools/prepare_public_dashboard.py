"""Build a same-origin dashboard copy without editing the working rmf-web tree."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def replace_once(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Unsupported rmf-web source at {path.name}; refusing to patch')
    path.write_text(text.replace(old, new, 1))


def main():
    web, runtime, overlay = map(lambda value: Path(value).resolve(), sys.argv[1:])
    expected = 'e2861c292bb27014435452e74faa825ecb0e8d91'
    actual = subprocess.check_output(['git', '-C', str(web), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != expected:
        raise RuntimeError('Public dashboard requires the audited rmf-web e2861c2 checkout')
    source = runtime / 'dashboard-source'
    if source.exists():
        shutil.rmtree(source)
    shutil.copytree(web / 'packages/dashboard', source,
                    ignore=shutil.ignore_patterns('node_modules', 'build', '.git', '.env*'))
    # Resolve pnpm's relative links before moving the app outside its workspace.
    modules = source / 'node_modules'
    modules.mkdir()
    for directory in (web / 'node_modules', web / 'node_modules/.pnpm/node_modules',
                      web / 'packages/dashboard/node_modules'):
        for dependency in directory.iterdir():
            link = modules / dependency.name
            if link.is_symlink():
                link.unlink()
            link.symlink_to(dependency.resolve(), target_is_directory=dependency.is_dir())
    app_config = source / 'src/app-config.ts'
    replace_once(app_config, 'const trajServer = process.env.REACT_APP_TRAJECTORY_SERVER;',
                 "const trajServer = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/trajectory`;")
    replace_once(app_config, 'rmfServerUrl: process.env.REACT_APP_RMF_SERVER,',
                 "rmfServerUrl: `${window.location.origin}/api`,")
    shutil.copyfile(overlay / 'public-map-url.ts', source / 'src/util/public-map-url.ts')
    ingress = source / 'src/components/rmf-app/rmf-ingress.ts'
    replace_once(ingress, "import appConfig from '../../app-config';",
                 "import appConfig from '../../app-config';\nimport { publicMapImageUrl } from '../../util/public-map-url';")
    replace_once(ingress,
                 'buildingMapObs: Observable<BuildingMap> = this._convertSioToRxObs((handler) =>',
                 'buildingMapObs: Observable<BuildingMap> = this._convertSioToRxObs<BuildingMap>((handler) =>')
    replace_once(ingress, '''    this._sioClient.subscribeBuildingMap(handler),
  );''', '''    this._sioClient.subscribeBuildingMap(handler),
  ).pipe(map((building) => ({
    ...building,
    levels: building.levels.map((level) => ({
      ...level,
      images: level.images.map((image) => ({
        ...image,
        data: publicMapImageUrl(image.data, appConfig.rmfServerUrl),
      })),
    })),
  })));''')
    output = runtime / 'webroot/dashboard.next'
    # Match the working dashboard's pnpm/Jest compatibility setting.
    env = dict(os.environ, NODE_ENV='production', CI='false', SKIP_PREFLIGHT_CHECK='true',
               GENERATE_SOURCEMAP='false',
               PUBLIC_URL='/', BUILD_PATH=str(output), REACT_APP_AUTH_PROVIDER='stub',
               REACT_APP_RMF_SERVER='http://127.0.0.1:8088/api',
               REACT_APP_TRAJECTORY_SERVER='ws://127.0.0.1:8088/trajectory')
    node = web / '.brin-tools/node-v16.20.2-linux-x64/bin/node'
    build = web / 'packages/dashboard/node_modules/react-scripts/scripts/build.js'
    build_log = runtime / 'build.log'
    print(f'Building public dashboard; log: {build_log}', flush=True)
    with build_log.open('w') as log:
        result = subprocess.run([str(node), str(build)], cwd=source, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join(build_log.read_text().splitlines()[-40:]), file=sys.stderr)
        raise SystemExit(result.returncode)
    destination = runtime / 'webroot/dashboard'
    if destination.exists():
        shutil.rmtree(destination)
    output.rename(destination)
    print(f'Compiled successfully. Public dashboard ready: {destination}')


if __name__ == '__main__':
    main()
