import json
import pandas as pd
import pytest

from quantaalpha.research import experiment
from quantaalpha.research.jobs import execute_task
from quantaalpha.research.store import ResearchStore


def evaluation(*args):
    return {'metrics': {'annualized_return': -0.01, 'gross_annualized_return': 0.02,
                        'information_ratio': -0.2, 'max_drawdown': -0.03},
            'equity': [], 'diagnostics': {'duration_ms': 1}}


def test_bad_proposal_counts_against_budget_and_next_candidate_still_executes(monkeypatch, tmp_path):
    protocol = experiment.create_demo_protocol(tmp_path / 'fixture')
    proposals, runs = [], []

    def propose(index, *args):
        proposals.append(index)
        if index == 0:
            raise ValueError('Unsupported candidate parameter')
        return experiment.validate_candidate({'family': 'momentum'}, index), 'valid next proposal'

    monkeypatch.setattr(experiment, '_llm_candidate', propose)
    monkeypatch.setattr(experiment, '_run_candidate', lambda *args: (runs.append(args[4]) or evaluation()))
    result = experiment.run_research(protocol, {'planner': 'llm', 'budget': 2, 'run_ablation': True, 'output_dir': str(tmp_path / 'runs')})
    assert proposals == [0, 1, 0, 1]
    assert runs == ['research', 'research']
    for key in ('with_memory', 'without_memory'):
        assert result['ablation'][key]['evaluations'] == 2
        assert result['ablation'][key]['failed_trials'] == 1
    assert result['trials'][0]['failure_tags'] == ['proposal_rejected']
    assert result['trials'][0]['metrics'] == {}
    assert result['holdout'] is None
    assert json.loads((tmp_path / 'runs/with_memory/trials.json').read_text())[0]['status'] == 'failed'


def test_all_rejected_proposals_remain_available_in_failed_job(monkeypatch, tmp_path):
    protocol = experiment.create_demo_protocol(tmp_path / 'fixture')
    store = ResearchStore(tmp_path / 'store')
    entry = store.create_protocol(protocol)
    task = store.start_task(entry['id'], {'budget': 2, 'planner': 'llm'})
    monkeypatch.setattr(experiment, '_llm_candidate', lambda *args: (_ for _ in ()).throw(ValueError('invalid proposal')))
    monkeypatch.setattr(experiment, '_run_candidate', lambda *args: pytest.fail('Rejected proposal must not execute'))
    assert execute_task(task['id'], store=store)['status'] == 'failed'
    saved = store.get_protocol(entry['id'])
    assert saved['state'] == 'failed'
    assert len(saved['result']['trials']) == 2
    assert saved['result']['best_candidate'] is None
    assert saved['result']['holdout'] is None
    assert store.list_memories() == []  # Invalid JSON is not financial failure evidence.


@pytest.mark.parametrize('bad', [float('inf'), float('-inf'), float('nan'), None, True, '0.5'])
def test_nonfinite_or_non_numeric_worker_metric_is_not_a_success(bad):
    metrics = {'annualized_return': bad, 'information_ratio': 1, 'max_drawdown': -0.1}
    frame = pd.DataFrame({'date': ['2021-01-01'], 'equity': [1.0], 'benchmark': [1.0], 'drawdown': [0.0], 'daily_excess_return': [0.0]})
    with pytest.raises(ValueError, match='finite'):
        experiment._validate_worker_evidence(metrics, frame)


def test_infinite_curve_is_not_hidden_as_a_valid_equity_series():
    frame = pd.DataFrame({'date': ['2021-01-01'], 'equity': [float('inf')], 'benchmark': [1.0], 'drawdown': [0.0], 'daily_excess_return': [0.0]})
    with pytest.raises(ValueError, match='non-finite'):
        experiment._validate_worker_evidence(evaluation()['metrics'], frame)


@pytest.mark.parametrize('failed_arm', ['both', 'without_memory'])
def test_failed_ablation_arm_retains_full_budget_without_selecting_invalid_candidate(monkeypatch, tmp_path, failed_arm):
    protocol = experiment.create_demo_protocol(tmp_path / 'fixture')
    calls = []

    def propose(index, *args):
        calls.append(index)
        if failed_arm == 'both' or len(calls) > 2:
            raise ValueError('invalid proposal')
        return experiment.validate_candidate({'family': 'momentum'}, index), 'valid'

    monkeypatch.setattr(experiment, '_llm_candidate', propose)
    monkeypatch.setattr(experiment, '_run_candidate', evaluation)
    config = {'planner': 'llm', 'budget': 2, 'run_ablation': True, 'output_dir': str(tmp_path / 'runs')}
    if failed_arm == 'both':
        with pytest.raises(experiment.ResearchExecutionError) as caught:
            experiment.run_research(protocol, config)
        result = caught.value.partial_result
        assert result['best_candidate'] is None
    else:
        result = experiment.run_research(protocol, config)
        assert result['best_candidate'] is not None
    assert calls == [0, 1, 0, 1]
    for key in ['with_memory', 'without_memory']:
        assert result['ablation'][key]['evaluations'] == 2
    assert result['ablation']['without_memory']['failed_trials'] == 2
    assert result['ablation']['without_memory']['best_candidate'] is None
    assert result['ablation']['without_memory']['metrics'] == {}
    assert result['holdout'] is None
