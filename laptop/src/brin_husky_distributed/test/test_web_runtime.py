"""Physical Web endpoints, wall time and cross-host launch wiring."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

from launch import LaunchContext
from launch.utilities import perform_substitutions
from launch_ros.utilities import evaluate_parameters
import pytest

from brin_husky_distributed import profile_info, profiles, web_runtime
from test_distributed import context, load


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('uri', ['', 'ws://192.168.0.50:8000/_internal',
                                 'wss://rmf-laptop.local/_internal'])
def test_valid_robot_web_endpoint(uri):
    assert web_runtime.validate_server_uri(uri, remote=True) == uri


@pytest.mark.parametrize('host', ['localhost', 'LOCALHOST.', 'rmf.localhost',
                                  '127.0.0.1', '127.1.2.3', '0.0.0.0',
                                  '[::1]', '[::]', '[::ffff:127.0.0.1]'])
def test_robot_rejects_endpoint_that_cannot_reach_laptop(host):
    with pytest.raises(ValueError, match='laptop LAN address'):
        web_runtime.validate_server_uri(f'ws://{host}:8000/_internal', remote=True)


@pytest.mark.parametrize('uri', ['http://192.168.0.50:8000/_internal',
                                 'ws://', 'ws://user:secret@laptop/_internal',
                                 'ws://laptop:0/_internal', 'ws://laptop:abc',
                                 'ws://laptop:65536', 'ws://[::1',
                                 'ws://laptop/_internal#fragment'])
def test_malformed_endpoints_fail_before_launch(uri):
    with pytest.raises(ValueError):
        web_runtime.validate_server_uri(uri)


def test_laptop_can_use_local_endpoint():
    uri = 'ws://localhost:8000/_internal'
    assert web_runtime.validate_server_uri(uri) == uri


def test_dispatcher_and_onboard_adapter_receive_web_uri_in_wall_time(monkeypatch):
    uri = 'ws://192.168.0.50:8000/_internal'
    ctx = context(dispatch='true')
    ctx.launch_configurations['server_uri'] = uri
    laptop = load('laptop', monkeypatch)
    nodes = laptop.setup(ctx)
    dispatcher = evaluate_parameters(ctx, nodes[1]._Node__parameters)[0]
    assert dispatcher['server_uri'] == uri
    assert dispatcher['use_sim_time'] is False
    robot = load('robot', monkeypatch)
    handler, bridge, preflight = robot.setup(ctx)
    adapter = handler.event_handler.handle(SimpleNamespace(returncode=0), ctx)[0]
    params = evaluate_parameters(ctx, adapter._Node__parameters)[0]
    assert params['server_uri'] == uri
    assert params['use_sim_time'] is False
    assert tuple(params['robots']) == ('husky_0',)
    ctx.launch_configurations['server_uri'] = 'ws://localhost:8000/_internal'
    with pytest.raises(ValueError, match='laptop LAN address'):
        robot.setup(ctx)


def test_web_launch_overrides_inherited_simulation_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('RMF_SERVER_USE_SIM_TIME', 'true')
    spec = importlib.util.spec_from_file_location(
        'physical_web_launch', ROOT / 'brin_husky_distributed/launch/web.launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'web_paths',
                        lambda root: (Path(root) / '.venv/bin/python', Path(root)))
    monkeypatch.setattr(module, 'get_package_share_directory',
                        lambda package: str(ROOT / package))
    ctx = LaunchContext()
    ctx.launch_configurations.update({
        'web_root': str(tmp_path / 'web'), 'runtime_dir': str(tmp_path / 'real'),
        'api_host': '192.168.0.50', 'public_url': 'http://192.168.0.50:8000'})
    process, = module.setup(ctx)
    env = {perform_substitutions(ctx, key): perform_substitutions(ctx, value)
           for key, value in process.process_description.additional_env}
    assert env['RMF_SERVER_USE_SIM_TIME'] == 'false'
    assert env['BRIN_WEB_API_HOST'] == '192.168.0.50'
    assert env['BRIN_WEB_RUNTIME'] == str(tmp_path / 'real')


def test_physical_api_config_uses_separate_database_and_real_time(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, 'api_server.default_config',
                        SimpleNamespace(config={'host': '127.0.0.1'}))
    monkeypatch.setenv('BRIN_WEB_RUNTIME', str(tmp_path / 'real'))
    monkeypatch.setenv('BRIN_WEB_API_HOST', '192.168.0.50')
    monkeypatch.setenv('BRIN_WEB_PUBLIC_URL', 'http://192.168.0.50:8000')
    spec = importlib.util.spec_from_file_location(
        'physical_api_config', ROOT / 'brin_husky_distributed/web/api_config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.config['ros_args'] == ['-p', 'use_sim_time:=false']
    assert module.config['host'] == '192.168.0.50'
    assert module.config['db_url'] == 'sqlite://' + str(tmp_path / 'real/api.sqlite3')
    assert Path(module.config['cache_directory']).is_dir()


def test_web_revision_and_runtime_are_checked(monkeypatch, tmp_path):
    monkeypatch.setattr(web_runtime.subprocess, 'run',
                        lambda *args, **kwargs: SimpleNamespace(stdout='wrong-revision'))
    with pytest.raises(ValueError, match='reviewed Humble revision'):
        web_runtime.web_paths(tmp_path)
    monkeypatch.setattr(web_runtime.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(stdout=web_runtime.WEB_REVISION))
    with pytest.raises(FileNotFoundError, match='incomplete'):
        web_runtime.web_paths(tmp_path)


def test_profile_info_lists_destinations_from_the_selected_graph(monkeypatch):
    monkeypatch.setattr(profiles, 'get_package_share_directory',
                        lambda package: str(ROOT / package))
    result = profile_info.profile_info('banyak_simpangan')
    assert result['name'] == 'banyak_simpangan'
    assert len(result['digest']) == 64
    assert len(result['places']['L1']['ws_p0']) == 2
    assert 'husky_0' in result['places']['L1']
