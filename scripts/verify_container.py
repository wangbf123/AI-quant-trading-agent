"""Exercise a running application image, including actual Qlib work.

Set AQR_TEST_URL if the container is published on a different local test port.
This script deliberately uses synthetic prices and never calls a model account.
"""
import json
import os
from pathlib import Path
import time

import httpx


def main():
    url = os.getenv('AQR_TEST_URL', 'http://127.0.0.1:8001')
    artifacts = Path(os.getenv('AQR_QA_DIR', 'data/results/container-qa'))
    artifacts.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=url, trust_env=False, timeout=30) as client:
        for _ in range(60):
            try:
                if client.get('/api/health').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(1)
        else:
            raise TimeoutError('Container API did not start')
        assert 'Agentic Quant Research Platform' in client.get('/').text
        capabilities = client.get('/api/v1/research/overview').json()['data']['capabilities']
        assert capabilities['qlib'] and capabilities['torch']
        created = client.post('/api/v1/research/demo', json={'budget': 2, 'seed': 42, 'use_memory': True})
        assert created.status_code == 200, created.text
        protocol_id = created.json()['data']['protocol']['id']
        path = '/api/v1/research/protocols/' + protocol_id

        def wait_for(state):
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                entry = client.get(path).json()['data']['protocol']
                if entry['state'] == state:
                    return entry
                if entry['state'] in ['failed', 'interrupted', 'finalization_failed']:
                    raise AssertionError(entry['task'].get('error'))
                time.sleep(2)
            raise TimeoutError('Container did not finish: ' + state)

        entry = wait_for('researched')
        assert entry['result']['holdout'] is None
        assert all(trial['status'] == 'completed' for trial in entry['result']['trials'])
        selected = entry['result']['best_candidate']['id']
        assert client.post(path + '/freeze', json={'candidate_id': selected}).status_code == 200
        assert client.post(path + '/finalize').status_code == 200
        entry = wait_for('finalized')
        assert len(entry['result']['holdout']['equity']) == 92
        assert client.post(path + '/finalize').status_code == 409
        exported = client.get(path + '/export').json()
        (artifacts / 'container-export.json').write_text(json.dumps(exported, ensure_ascii=False, indent=2))
    print(json.dumps({'status': 'passed', 'protocol_id': protocol_id, 'checks': ['compiled workbench', 'Qlib and CPU PyTorch installed', 'two real Qlib research trials', 'frozen holdout real evaluation', 'repeat holdout denied', 'evidence export'], 'model_account_calls': 'deferred'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
