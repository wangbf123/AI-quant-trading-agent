from quantaalpha.research.report import render_research_report


def entry():
    return {'id': 'test-protocol', 'name': '<unsafe> | title', 'state': 'researched',
            'protocol': {'name': 'test', 'source': 'synthetic', 'dataset_fingerprint': 'fingerprint'},
            'result': {'trials': [{'id': 'one', 'strategy': {'name': 'candidate'}, 'status': 'completed',
                                   'metrics': {'annualized_return': -0.1, 'information_ratio': 0.0}}],
                       'holdout': None, 'memories': [], 'secret': 'never-export-this'}}


def test_report_retains_negative_zero_and_missing_results_without_exporting_secrets():
    report = render_research_report(entry())
    assert '-10.00%' in report
    assert '0.000' in report
    assert '尚未取得最终样本外结果' in report
    assert '合成数据' in report
    assert 'never-export-this' not in report
    assert '<unsafe>' not in report
    assert r'\|' in report


def test_final_report_uses_actual_holdout_and_ablation_counts():
    document = entry()
    document['result']['holdout'] = {'metrics': {'annualized_return': -0.2}}
    document['result']['ablation'] = {key: {'budget': 3, 'evaluations': 3, 'metrics': {}} for key in ['with_memory', 'without_memory']}
    report = render_research_report(document)
    assert '-20.00%' in report
    assert report.count('3 / 3') == 2
    assert '不回流' in report


def test_report_can_be_regenerated_from_json_evidence_export():
    document = entry()
    document['protocol']['id'] = document.pop('id')
    document.pop('name')
    report = render_research_report(document)
    assert '`test-protocol`' in report
    assert '-10.00%' in report
