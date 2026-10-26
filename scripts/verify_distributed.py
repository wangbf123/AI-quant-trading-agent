"""Acceptance for the optional PostgreSQL + Redis/RQ profile.

Requires existing services via AQR_DATABASE_URL / AQR_REDIS_URL. Runs real
Qlib experiments, not a queue ping, and writes a reproducibility artifact.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from rq import Queue
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'frontend-v2' / 'backend'))
from research_api import create_research_router
from quantaalpha.research.jobs import execute_task
from quantaalpha.research.store import ResearchStore


def main():
    assert os.environ.get('AQR_DATABASE_URL', '').startswith('postgresql'), 'PostgreSQL URL required'
    assert os.environ.get('AQR_REDIS_URL'), 'Redis URL required'
    root = Path(os.getenv('AQR_DISTRIBUTED_QA_DIR', 'data/results/distributed-qa')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    store = ResearchStore(root, os.environ['AQR_DATABASE_URL'])
    redis = Redis.from_url(os.environ['AQR_REDIS_URL'])
    assert redis.ping()
    app = FastAPI()
    app.include_router(create_research_router(ROOT, store=store))

    def worker():
        with (root / 'worker.log').open('a') as log:
            result = subprocess.run([sys.executable, '-m', 'quantaalpha.research.jobs', '--burst'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        assert result.returncode == 0, (root / 'worker.log').read_text()[-4000:]

    with TestClient(app) as client:
        created = client.post('/api/v1/research/demo', json={'budget': 2, 'seed': 42})
        assert created.status_code == 200, created.text
        entry = created.json()['data']['protocol']
        protocol_id = entry['id']
        assert entry['state'] == 'running'
        assert Queue(os.getenv('AQR_QUEUE_NAME', 'aqr-research'), connection=redis).count >= 1
        worker()
        entry = store.get_protocol(protocol_id)
        assert entry['state'] == 'researched', entry
        assert entry['result']['holdout'] is None
        assert len(entry['result']['trials']) == 2
        task_id = entry['active_task_id']
        assert execute_task(task_id, store=store)['status'] == 'ignored'
        base = f'/api/v1/research/protocols/{protocol_id}'
        selected = entry['result']['best_candidate']['id']
        assert client.post(base + '/freeze', json={'candidate_id': selected}).status_code == 200
        assert client.post(base + '/finalize').status_code == 200
        worker()
        entry = store.get_protocol(protocol_id)
        assert entry['state'] == 'finalized', entry
        assert entry['result']['holdout']['equity']
        assert client.post(base + '/finalize').status_code == 409
        with store.engine.connect() as connection:
            version = connection.execute(text('select version()')).scalar()
        artifact = client.get(base + '/export').json()
        (root / 'distributed-export.json').write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
    print(json.dumps({'status': 'passed', 'postgres': version, 'redis_version': redis.info('server')['redis_version'], 'protocol_id': protocol_id, 'checks': ['PostgreSQL persistence', 'Redis enqueue', 'RQ worker real Qlib research', 'duplicate delivery ignored', 'frozen-candidate holdout through RQ', 'repeat-finalization denied'], 'artifact': str(root / 'distributed-export.json')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
