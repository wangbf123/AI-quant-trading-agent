from pathlib import Path

from quantaalpha.research.jobs import execute_task
from quantaalpha.research.memory import EconomicMemoryStore
from quantaalpha.research.store import ResearchStore


def test_failed_job_retains_committed_validation_observations(monkeypatch, tmp_path):
    from quantaalpha.research import experiment
    store = ResearchStore(tmp_path / 'store')
    entry = store.create_protocol({'name': 'failure retention', 'dataset_fingerprint': 'failure-data'})
    task = store.start_task(entry['id'], {'use_memory': True})

    def failed_run(protocol, config, progress):
        context = {'purpose': 'validation', 'dataset_fingerprint': 'failure-data', 'execution_fingerprint': 'costs-v1', 'validation_window': ['2021-01-01', '2021-12-31']}
        with EconomicMemoryStore(Path(config['output_dir']) / 'with_memory' / 'memory.sqlite') as memory:
            memory.record(context, {'execution_success': False}, {'name': 'failed candidate'})
        raise RuntimeError('Model training failed')

    monkeypatch.setattr(experiment, 'run_research', failed_run)
    assert execute_task(task['id'], store=store)['status'] == 'failed'
    assert store.get_protocol(entry['id'])['state'] == 'failed'
    saved = store.list_memories('failure-data')
    assert len(saved) == 1
    assert saved[0]['category'] == 'execution_failure'
    assert saved[0]['source_split'] == 'validation'
