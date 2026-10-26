# 工程验收记录

日期：2026-10-26。基于导入的 QuantaAlpha 提交 `b7ceb27b1001261d7a95b209a963664ae1f8ab23`，在 Linux / Python 3.12.14 / Node 24 环境验证。本记录将软件可运行性与模型研究效果分开。

## 已通过

| 检查 | 实际结果 |
| --- | --- |
| Python 测试 | 42 passed：经济失败分类、上下文隔离、记忆钩子、真实交易日 purge、缺失指标拒绝、候选约束、等预算、冻结与重复最终评估、密钥掩码与失败任务记忆保留 |
| 模型协议 | 通过本地 HTTP 协议服务调用上游 APIBackend、OpenAI SDK 及 Anthropic SDK；覆盖 Step Plan 路径、api-key/Bearer 头、模型名、候选 JSON 和 holdout 不进入提示词。此项不是外部模型效果测试 |
| 前端 | TypeScript 严格编译与 Vite 生产构建通过；修复上游缺失依赖和未使用导入 |
| 真实 Qlib 链路 | 本地合成 provider → 上游因子表达式 → LightGBM → Qlib SimulatorExecutor / TopkDropoutStrategy → 成本后指标与净值 CSV |
| 浏览器完整流程 | Chromium 中提交实验，2 次有记忆 + 2 次无记忆真实训练回测，冻结候选，运行一次最终 holdout，导出证据 |
| 最终评估约束 | 浏览器验收的重复 finalize 返回 409；并发单元测试也只允许一个数据库领取 |
| 移动端 | 390 像素视口无页面横向溢出，未捕获到浏览器脚本异常 |
| PostgreSQL | PostgreSQL 16.15 中真实持久化协议、任务、结果和记忆 |
| Redis / RQ | Redis 7.4.11、RQ 2.12.0 实际入队并执行 2 次 Qlib 研究实验与最终 holdout，重复投递不重复执行 |
| CLI 完整流程 | `aqr demo --budget 2 --ablation --finalize` 已执行，最终输出 92 个 holdout 净值点及两组各 2 次实验 |
| 安装复用 | `scripts/setup.sh` 已在既有隔离环境重复运行，安装、pip check、npm ci 和生产构建通过 |
| 源码分发 | Python wheel 内容已检查，含 174 个包文件与提示词 YAML；不含前端 node_modules |
| CI | 已提供 GitHub Actions，执行锁定安装、测试、前端构建及真实 Qlib smoke；配置已解析，远端运行等待推送 |
| Docker 应用 | 最终镜像构建成功；UID 10001 启动健康，容器内真实运行 2 次 Qlib 研究及最终 holdout，并通过证据导出、重复评估拒绝和 React 页面渲染验收 |
| Compose | `docker compose config --quiet` 通过 |

Qlib 0.9.7、LightGBM 4.7.0、NumPy 1.26.4、Pandas 2.3.3；完整已验证依赖保存在 `requirements/research.lock`。

## 测试产物

本云实例的浏览器截图与证据包：`/workspace/agent-dev/quant-qa/`，含 `validation.png`、`completed-desktop.png`、`completed-mobile.png`、`research-export.json`、`model-settings.png`、`container-workbench.png` 和 `container-export.json`。PostgreSQL / Redis 证据包位于 `/workspace/agent-dev/quant-distributed-qa/distributed-export.json`。这些目录包含运行产物，未作为业务源码提交。

通过 `scripts/verify_browser.py` 与 `scripts/verify_distributed.py` 可产生新的验收协议和证据；已完成的协议不会重新执行最终测试。

## 真实结果及解释

合成数据验收中的候选可以出现负收益。浏览器验收选择的候选，验证窗成本后超额年化约 -0.55%，最终 holdout 约 -11.50%；平台保留这些负结果与成本侵蚀记忆。该数字只说明结果按实际计算保存，没有市场投资含义。

一次、单种子的有／无记忆差异只证明记忆机制改变提案且预算相同，尚不足以证明记忆提高样本外收益。进一步研究需要真实数据、多随机种子、固定成本假设与统计检验。

## 尚未验证的能力

- 外部真实 LLM 服务：已按截图配置 StepFun Step Plan、step-5-preview、Anthropic Messages；按用户要求暂缓真实账号联调，密钥需通过安全环境设置绑定。
- 真实市场数据上的因子效果及回测稳健性；演示 provider 为明确标记的合成数据。
- PyTorch 模型训练、C++ 高频执行与实盘交易网关。
- 当前机器之外的新任务恢复、环境发布及远程部署。

最终镜像为 `agentic-quant-research:local`，本次镜像 ID 为 `sha256:c9d982ec0efcfacf3b9c44cbbef798d6c696b13187b65596ef340f7c1ab4f1dd`。当前云机使用 Docker vfs，已把大型依赖安装合并到最后一层，避免后续 COPY 重复复制依赖。机构代理 CA 通过 BuildKit secret 挂载，TLS 校验保持启用。构建、容器健康检查和容器内完整 Qlib 流程均已实际验证。

已知非阻塞项：上游依赖产生弃用警告，Vite 提示主 bundle 大于 500 kB；没有因此跳过断言或关闭 TypeScript 检查。
