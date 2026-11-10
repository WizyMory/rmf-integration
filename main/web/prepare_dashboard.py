#!/usr/bin/env python3
"""Prepare a reproducible dashboard overlay without changing the rmf-web checkout."""
import argparse
from pathlib import Path
import shutil
import subprocess

REVISION = 'e2861c292bb27014435452e74faa825ecb0e8d91'


def replace_once(path, old, new):
    value = path.read_text()
    if value.count(old) != 1:
        raise RuntimeError(f'Unsupported dashboard source: {path}: expected one match')
    path.write_text(value.replace(old, new, 1))


def prepare(web, destination):
    actual = subprocess.check_output(['git', '-C', str(web), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != REVISION:
        raise RuntimeError(f'Expected rmf-web {REVISION}, got {actual}')
    # This directory is generated; never delete an arbitrary caller-supplied tree.
    marker = destination / '.brin-generated'
    if destination.exists():
        if not marker.is_file():
            raise RuntimeError(f'Refusing to replace non-generated directory: {destination}')
        shutil.rmtree(destination)
    shutil.copytree(web/'packages/dashboard', destination,
                    ignore=shutil.ignore_patterns('node_modules', 'build', '.git', '.env*'))
    marker.touch()
    modules = destination/'node_modules'
    modules.mkdir()
    for directory in (web/'node_modules', web/'node_modules/.pnpm/node_modules',
                      web/'packages/react-components/node_modules', web/'packages/dashboard/node_modules'):
        for dependency in directory.iterdir():
            if dependency.name == '.cache':
                continue
            if dependency.name.startswith('@') and dependency.is_dir():
                scope = modules/dependency.name
                scope.mkdir(exist_ok=True)
                for item in dependency.iterdir():
                    link = scope/item.name
                    if link.is_symlink():
                        link.unlink()
                    link.symlink_to(item.resolve(), target_is_directory=item.is_dir())
                continue
            link = modules/dependency.name
            if link.is_symlink():
                link.unlink()
            link.symlink_to(dependency.resolve(), target_is_directory=dependency.is_dir())
    overlay = Path(__file__).resolve().parent/'overlay'
    shutil.copytree(overlay, destination, dirs_exist_ok=True)
    appbar = destination/'src/components/appbar.tsx'
    replace_once(appbar, "import useGetUsername from '../hooks/useFetchUser';",
        "import useGetUsername from '../hooks/useFetchUser';\nimport { PatrolTaskDialog } from './brin/patrol-task-dialog';\nimport { RobotBatteryPanel } from './brin/battery-panel';")
    replace_once(appbar, '  const [openCreateTaskForm, setOpenCreateTaskForm] = React.useState(false);',
        '  const [openCreateTaskForm, setOpenCreateTaskForm] = React.useState(false);\n  const [quickPatrol, setQuickPatrol] = React.useState(true);')
    replace_once(appbar, 'onClick={() => setOpenCreateTaskForm(true)}',
        'onClick={() => { setQuickPatrol(true); setOpenCreateTaskForm(true); }}')
    replace_once(appbar, '      </HeaderBar>', '      </HeaderBar>\n      <RobotBatteryPanel />')
    replace_once(appbar, '      {openCreateTaskForm && (', '''      {openCreateTaskForm && quickPatrol && (
        <PatrolTaskDialog waypoints={waypointNames} user={username || 'unknown user'}
          onClose={() => setOpenCreateTaskForm(false)} onAdvanced={() => setQuickPatrol(false)}
          onSuccess={() => { setOpenCreateTaskForm(false); showAlert('success', 'Patrol diterima RMF'); }} />
      )}
      {openCreateTaskForm && !quickPatrol && (''')
    robots = destination/'src/components/robots/robots-app.tsx'
    replace_once(robots, "import { RobotDataGridTable, RobotTableData } from 'react-components';",
        "import { RobotTableData } from 'react-components';\nimport { RobotDataGridTable } from '../brin/robot-table';")
    summary = destination/'src/components/robots/robot-summary.tsx'
    replace_once(summary, "import { RobotDecommissionButton } from './robot-decommission';",
        "import { RobotDecommissionButton } from './robot-decommission';\nimport { batteryLabel, useBatteries } from '../brin/battery-panel';")
    replace_once(summary, '  const rmf = React.useContext(RmfAppContext);',
        '  const rmf = React.useContext(RmfAppContext);\n  const batterySample = useBatteries().find((s) => s.fleet === robot.fleet && s.robot === robot.name);')
    replace_once(summary, '''            <Typography variant="subtitle1">{`${
              robotState?.battery ? (robotState.battery * 100).toFixed(0) : 0
            }%`}</Typography>
            {robotState && (
              <>{showBatteryIcon(robot, robotState.battery ? robotState?.battery * 100 : 0)}</>
            )}''', '''            <Typography variant="subtitle1">{batteryLabel(batterySample)}</Typography>
            {batterySample && !batterySample.stale && batterySample.soc != null
              ? <BatteryFull /> : <BatteryUnknown />}''')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('web', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(prepare(args.web.resolve(), args.destination.resolve()))
