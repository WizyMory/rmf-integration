"""Physical-system API config for rmf-web e2861c2 (ROS 2 Humble)."""
import os
from pathlib import Path

from api_server.default_config import config as defaults


runtime = Path(os.environ['BRIN_WEB_RUNTIME'])
runtime.mkdir(parents=True, exist_ok=True)
(runtime / 'cache').mkdir(exist_ok=True)
config = dict(
    defaults,
    host=os.environ.get('BRIN_WEB_API_HOST', '127.0.0.1'),
    port=8000,
    public_url=os.environ.get('BRIN_WEB_PUBLIC_URL', 'http://localhost:8000'),
    db_url='sqlite://' + str(runtime / 'api.sqlite3'),
    cache_directory=str(runtime / 'cache'),
    ros_args=['-p', 'use_sim_time:=false'],
    timezone='Asia/Jakarta',
    log_level='INFO',
)
