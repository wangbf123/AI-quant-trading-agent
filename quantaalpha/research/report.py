"""Readable Markdown reports from persisted evidence, without model calls."""
import html
import math


def _text(value):
    return html.escape(str(value if value is not None else '—')).replace('|', r'\|').replace('\n', ' ')


def _number(value, percent=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return '—'
    return f'{value * 100:.2f}%' if percent else f'{value:.3f}'


def render_research_report(entry: dict) -> str:
    protocol = entry['protocol']
    result = entry.get('result') or {}
    source = (result.get('provenance') or {}).get('source', protocol.get('source', 'user_provider'))
    lines = [f"# 量化研究报告：{_text(entry.get('name', protocol.get('name')))}", '',
             f"- 协议：`{_text(entry.get('id', protocol.get('id')))}`", f"- 状态：{_text(entry['state'])}",
             f"- 数据来源：{'合成数据（仅用于工程验证）' if source == 'synthetic' else _text(source)}",
             f"- 数据指纹：`{_text(protocol.get('dataset_fingerprint'))}`", '',
             '## 时间窗口', '', '| 窗口 | 起始 | 结束 |', '| --- | --- | --- |']
    for key, title in [('train', '训练'), ('tune', '调参'), ('validation', '研究验证'), ('holdout', '最终封存')]:
        bounds = protocol.get(key) or ['—', '—']
        lines.append(f'| {title} | {_text(bounds[0])} | {_text(bounds[1])} |')
    lines += ['', '## 候选实验', '', '| 候选 | 状态 | 净超额年化 | 信息比率 | 超额最大回撤 | 失败标签 |', '| --- | --- | --- | --- | --- | --- |']
    for trial in result.get('trials', []):
        strategy = trial.get('strategy') or {}
        metrics = trial.get('metrics') or {}
        lines.append(f"| {_text(strategy.get('name', trial.get('id')))} | {_text(trial.get('status'))} | {_number(metrics.get('annualized_return'), True)} | {_number(metrics.get('information_ratio'))} | {_number(metrics.get('max_drawdown'), True)} | {_text(', '.join(trial.get('failure_tags', [])))} |")
    if not result.get('trials'):
        lines += ['', '尚无候选结果。']
    lines += ['', '## 最终样本外评估', '']
    holdout = result.get('holdout')
    if not holdout:
        lines += ['尚未取得最终样本外结果；研究验证指标不能替代最终样本外表现。']
    else:
        metrics = holdout.get('metrics') or {}
        lines += [f"- 成本后超额年化：{_number(metrics.get('annualized_return'), True)}",
                  f"- 信息比率：{_number(metrics.get('information_ratio'))}",
                  f"- 超额最大回撤：{_number(metrics.get('max_drawdown'), True)}",
                  '', '该观察用于最终报告，不回流候选生成和失败记忆。']
    ablation = result.get('ablation') or {}
    if 'with_memory' in ablation and 'without_memory' in ablation:
        lines += ['', '## 等预算消融', '', '| 分组 | 已尝试 / 预算 | 净超额年化 | 信息比率 |', '| --- | --- | --- | --- |']
        for key, title in [('with_memory', '有记忆'), ('without_memory', '无记忆')]:
            arm = ablation[key]
            metrics = arm.get('metrics') or {}
            lines.append(f"| {title} | {_text(arm.get('evaluations'))} / {_text(arm.get('budget'))} | {_number(metrics.get('annualized_return'), True)} | {_number(metrics.get('information_ratio'))} |")
        lines += ['', '单次种子差异仅用于工程对照，不证明统计显著性或真实市场盈利。']
    lines += ['', '## 经济性失败证据', '']
    for memory in result.get('memories', []):
        lines.append(f"- **{_text(memory.get('category'))}**：{_text(memory.get('description'))}")
    if not result.get('memories'):
        lines.append('暂无已记录的经济性失败证据。')
    lines += ['', '## 失败与复核', '']
    failures = [trial for trial in result.get('trials', []) if trial.get('error')]
    for trial in failures:
        lines.append(f"- {_text(trial.get('id'))}：{_text(trial['error'])}")
    if not failures:
        lines.append('未记录候选错误。详细配置、原始指标、事件和冻结摘要请查看同协议的 JSON 证据包。')
    lines += ['', '研究报告由持久化结果确定性生成；缺失指标显示为“—”，没有补造收益或模型结论。', '']
    return '\n'.join(lines)
