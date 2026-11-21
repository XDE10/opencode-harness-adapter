# Harness Adapters 复现差距

本文记录三道普通 Python 功能题的早期 CPU 基线。当前已固定 Qwen3-8B，单卡配置和最新边界见 [单卡流程](colab-g4.md)。

| 项目 | 公开实现 | 本仓库与剩余差距 |
| --- | --- | --- |
| 公开评测轨迹 | 每题一条 JSONL，含运行维度、task、reward（1/0/null）、error、耗时、代理统计的模型调用/生成 token/工具调用数及文件。文件含 ATIF 轨迹、CLI 日志、Harbor 配置和 verifier 输出。详见[公开轨迹字段](https://huggingface.co/buckets/harness-hub/harness-adapters-trajectories)。 | 本仓库保留 OpenCode JSON 事件、工具调用、补丁和独立判分。CLI 事件不等同 ATIF，也不能提供代理侧真实 token 或请求计数。脚本 mock 只验证接线，无法衡量模型能力。 |
| 模型侧训练轨迹 | OpenEnv 捕获引擎原始数据。每回合有 `node_id`、`prompt_token_ids`、`completion_token_ids`、`per_token_logps` 和覆盖两段的 `loss_mask`；prompt 位置为零，排除辅助调用及丢弃重试。详见 [TRL OpenEnv 契约](https://huggingface.co/docs/trl/openenv)。 | 真实试跑也只能产生当前 CLI 指标。还需在授权模型服务接入捕获并验证对齐；既有 mock 和下一步个人试跑都不能提供可用于 GRPO 的轨迹。公开评测档案也不作训练数据。 |
| Reward | [发布模型卡](https://huggingface.co/harness-hub/Qwen3.8-27B-opencode-adapted#training) 的训练使用 verifier 的 correctness（回退 reward）和权重 0.1 的工具效率项。[固定版本 TRL 示例](https://github.com/huggingface/trl/blob/b2686bf5c300756cdf878b84f83a48f794e2fb94/examples/async_grpo_harbor/async_grpo_harbor.py#L120-L157) 的示例权重为 0.3，仅在 correctness≥1 时叠加经截断的 1−工具数/15；无法评分的 rollout 从组基线排除。两处参数分别记录。 | CPU 验收只核对独立正确性，执行错误和超时单列。没有效率训练奖励或 GRPO。 |
| 采样协议 | 报告先用基础模型每题 4 次筛难度（部分分层样本 8 次）；发布训练为每题 8 次、温度 0.8、thinking off、50 步及 1,800 秒上限。详见[报告](https://huggingface.co/blog/harness-adapters-at-scale)和[模型卡](https://huggingface.co/harness-hub/Qwen3.8-27B-opencode-adapted#training)。 | 固定三个合成任务和本地 CLI 参数。脚本 mock 固定回复；真实试跑计划每题一次。服务采样、累计调用及 token 预算未与原评测对齐。 |
| 评测协议 | OpenCode 上比较基础模型与 LoRA；默认 thinking off、温度 0.8、top-p 1.0、同任务同配置、一次尝试。评测为 SWE-bench Pro hard 51（2 小时）与 Terminal-Bench 2.1（1 小时），各 100 步；报告设 131,072 总 token 上限，[归档](https://huggingface.co/buckets/harness-hub/harness-adapters-trajectories)列 thinking off/on 每次调用上限 8,192/32,768。另有按任务配对和仅双方均通过题目的效率统计。详见[模型卡](https://huggingface.co/harness-hub/Qwen3.8-27B-opencode-adapted#results)。 | 三道 CPU 功能题只作验收，不形成 benchmark 或训练结论。真实验证只缺已授权、符合指定模型与修订的可用隔离端点；后续训练和未见题配对评测另行处理。 |

## 基线证据

在同一 Codex Cloud 租用环境，从干净的 `b7d939a` 执行 `./scripts/install-opencode.sh && python3 -u harness/run.py`。退出码 0，OpenCode 2.2.7 版本及帮助检查通过。原始/参考/不完整对照三题均为 **fail / pass / fail**，共 **9/9** 符合预期。固定 mock 的边界题通过，记录 **4 次 HTTP 完成请求、2 次工具调用**，依次为 read 和 write。原始工件在本地忽略目录 `artifacts/run-RUN/`。当时 Docker 没有运行中的模型容器，也未提供授权端点。

## 改进版交付验收

执行 `./scripts/run-harness.sh` 验证实现提交 `b48a8a9`，退出码 0。本地原始证据为 `artifacts/run-RUN/`，不纳入 Git。

| 检查 | 基线 | 改进版实测 |
| --- | --- | --- |
| 固定题目与判分 | 九对照为 fail / pass / fail | 九项全同，逐项比较了断言结果；三题与判分文件相对 `b7d939a` 字节不变，夹具 15 个 SHA-256 锁定并检查 |
| OpenCode 行为 | 2.2.7，mock 的边界题通过，4 次完成请求与 2 次 CLI 工具调用 | 同版本，同判分，同调用数；另实测内置 mock 被试跑预检拒绝 |
| 真实端点预检 | 检查隔离网络和模型 ID | GET-only 隔离夹具通过，修订不匹配被拒；缺失容器退出 2、生成拒绝报告和零条尝试。日志 `artifacts/run-RUN/preflight.json` |
| 轨迹审计 | 每次尝试单独记录 | 增加可校验的 manifest 和按来源分组的报告，共 9 条判分对照和 1 条脚本 mock。工件 SHA-256 全部复核；10 条均无训练轨迹 |
| 回归测试 | 单次 CPU 验收 | 7 项回归测试通过，涵盖夹具变化、模型与修订、隔离网络、mock 和评分排除 |

报告 SHA-256 为 `010885653cb064f69a24d1b5b32e57979b787d07376f40bda5b8affa8fe8966f`，manifest SHA-256 为 `70839a98d3b530d8ef3507986b0627b7fc0d58af1ee90c78f6febcdddedc514b`。真实模型验证的唯一外部依赖仍是已授权且匹配指定模型及修订的隔离端点。真实试跑及训练均未执行。
