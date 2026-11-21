# 上游来源与本项目改动

| 上游与固定版本 | 路径或材料 | 本项目采用范围与许可 |
| --- | --- | --- |
| Hugging Face TRL `b2686bf5c300756cdf878b84f83a48f794e2fb94` | [`examples/async_grpo_harbor/async_grpo_harbor.py`](https://github.com/huggingface/trl/blob/b2686bf5c300756cdf878b84f83a48f794e2fb94/examples/async_grpo_harbor/async_grpo_harbor.py#L107-L141) | `tool_efficiency` 提取到 `colab/trl_reward.py`，将全局预算改成传入的参数，保留截断及缺失计数行为。保留原版权并注明修改，适用 [Apache-2.0](../LICENSES/Apache-2.0.txt)。 |
| 同一 TRL 修订 | [AsyncGRPO Harbor README](https://raw.githubusercontent.com/huggingface/trl/b2686bf5c300756cdf878b84f83a48f794e2fb94/examples/async_grpo_harbor/README.md) | 链接用于核对训练轨迹、会话工厂及双卡流程。未引入示例 README、launcher、异步训练器或上游数据。 |
| OpenEnv `0.7.0`，源码修订 `20d780889bd391cf9810b67912389f4d2228dfd6` | [`TrainingTrace` 定义](https://github.com/openenv/OpenEnv/blob/20d780889bd391cf9810b67912389f4d2228dfd6/src/openenv/core/harness/training.py) · [BSD-3-Clause](https://raw.githubusercontent.com/openenv/OpenEnv/20d780889bd391cf9810b67912389f4d2228dfd6/LICENSE) | 安装锁定 wheel 后直接调用核心捕获和 typed trace。OpenEnv 源码、wheel 及 TRL 示例使用的 `harbor_env.harness` 工厂均未纳入源码快照。 |
| HF OpenCode 模型卡 `9c6545360eb1fea3a1fb2d142e5c166a88ffc275` | [训练章节](https://huggingface.co/harness-hub/Qwen3.8-27B-opencode-adapted/blob/9c6545360eb1fea3a1fb2d142e5c166a88ffc275/README.md#training) | 参考 OpenCode 2.2.7、独立正确性、成功项工具效率权重 0.1 和同设置配对比较。模型卡标注 Apache-2.0，仓库只链接该卡并记录相关事实。 |

`colab/contracts.py` 对已验证的二值 Harbor 奖励调用该函数。预算 15、权重 0.1 仍从本项目锁定配置读取。TRL 示例本身的权重为 0.3。未评分尝试仍由本项目独立门槛排除。由于直接下载完整示例的公开 DNS 请求超时，移植只采用已按 Git 提交核对的这一小段源码。上游具体条目以固定链接为准。

`protocol/colab-g4-v1.json` 管理本仓库自己制定的 Qwen3-8B、`hermes`、较小预算、同步阶段和 LoRA rank 16。保留既有本地 OpenCode、Harbor Trial、独立 verifier 和捕获中继。参见 [NOTICE](../NOTICE)。
