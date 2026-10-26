> 这是合成数据工程验收的报告快照，来自实际 Qlib 运行；不代表市场盈利效果。复现命令见 [工程验收记录](../VALIDATION.md)。

# 量化研究报告：Synthetic daily research · 12 assets

- 协议：`57d4b823-a0d6-47c7-aaac-dc34c8824e11`
- 状态：finalized
- 数据来源：合成数据（仅用于工程验证）
- 数据指纹：`c017ae260097cfc39727561e1f384af2f85fa7b7226ad33bef49fa4a729005a5`

## 时间窗口

| 窗口 | 起始 | 结束 |
| --- | --- | --- |
| 训练 | 2020-03-26 | 2021-02-24 |
| 调参 | 2021-03-01 | 2021-05-21 |
| 研究验证 | 2021-05-26 | 2021-09-14 |
| 最终封存 | 2021-09-17 | 2022-01-24 |

## 候选实验

| 候选 | 状态 | 净超额年化 | 信息比率 | 超额最大回撤 | 失败标签 |
| --- | --- | --- | --- | --- | --- |
| price_volume · top 8 / drop 1 | completed | -12.75% | -4.434 | -4.93% | cost_drag, negative_net_return |
| low_volatility · top 8 / drop 1 | completed | -0.47% | -0.170 | -1.42% | cost_drag, negative_net_return |

## 最终样本外评估

- 成本后超额年化：-17.05%
- 信息比率：-4.824
- 超额最大回撤：-5.39%

该观察用于最终报告，不回流候选生成和失败记忆。

## 等预算消融

| 分组 | 已尝试 / 预算 | 净超额年化 | 信息比率 |
| --- | --- | --- | --- |
| 有记忆 | 2 / 2 | -0.47% | -0.170 |
| 无记忆 | 2 / 2 | -0.55% | -0.198 |

单次种子差异仅用于工程对照，不证明统计显著性或真实市场盈利。

## 经济性失败证据

- **cost_drag**：Observed execution costs materially reduced the gross result.
- **negative_net_return**：The observed validation return was negative after costs.
- **cost_drag**：Observed execution costs materially reduced the gross result.
- **negative_net_return**：The observed validation return was negative after costs.

## 失败与复核

未记录候选错误。详细配置、原始指标、事件和冻结摘要请查看同协议的 JSON 证据包。

研究报告由持久化结果确定性生成；缺失指标显示为“—”，没有补造收益或模型结论。
