# Colab G4 上的 OpenCode 单分支复现

目标是在已获授权的一张 Colab G4 96 GB GPU 上，复现 **真实 OpenCode 工具循环 → Harbor 独立测试 → OpenEnv 引擎捕获 → 冻结基础权重的 LoRA GRPO → 同题同预算对照**。目标模型是官方对话后训练版 `Qwen/Qwen3-8B`，权重 revision `b968826d9c46dd6066d109eabc6255188de91218`。Qwen3-8B 是一个同时支持 thinking 和 non-thinking 的正式模型，本实验使用同一权重的 non-thinking 模式。五个权重分片及 tokenizer、配置和分片索引的 SHA-256 均已锁定。本文复现方法，不比较或复刻原 27B 榜单分数。 [Qwen 固定版本模型卡](https://huggingface.co/Qwen/Qwen3-8B/tree/b968826d9c46dd6066d109eabc6255188de91218) · [Colab G4 说明](https://colab.research.google.com/notebooks/relnotes.ipynb)

## 同步执行顺序

1. **资格预检。** 核对本地 snapshot 的十个文件摘要、单张 G4 的型号和 VRAM、可用的本地 Harbor Docker、隔离策略和实际 Python/CUDA/vLLM/Transformers/PEFT 版本。保留 OpenCode 2.2.7、OpenEnv 0.7.0 的 typed capture 契约及其源码修订。Harbor 固定 0.25.0，已与 OpenEnv 0.7.0 安装并通过 CPU schema 检查；0.27.0 实测因 FastMCP 版本冲突不采用。只用本地资产，任务不继承账号、API key、代理凭据、宿主目录或 Docker socket。
2. **只 rollout。** 在可信侧加载已校验的 snapshot，以 vLLM BF16 服务，使用 Qwen 官方的 `hermes` 工具解析和模板硬开关 `enable_thinking=false`。采样写入 `protocol/colab-g4-v1.json`，温度 0.8、top-p 1.0、无 top-k/min-p 截断、无惩罚，首轮约束为 4,096 上下文、每次最多 512 输出 token、全程最多 2,048 输出 token / 12 次模型调用 / 180 秒。可信中继负责强制调用与生成预算，合成后端已验证该接线，真实引擎计数仍待实测。只许可到本地捕获中继的流量，任务端使用无权限占位符；OpenEnv 的短期捕获会话凭据也由可信侧注入。现有任务包故意默认 no-network，在正确的隔离中继接通前不得放开网络。 [Qwen vLLM 工具调用](https://qwen.readthedocs.io/en/latest/deployment/vllm.html#parsing-tool-calls) · [OpenEnv Harbor 捕获说明](https://huggingface.co/docs/openenv/main/environments/harbor)
3. **先验收三题。** `boundary`、`parsing`、`serialization` 各运行一次，每题须有真实工具调用、独立 verifier 二值判分、原始 OpenEnv TrainingTrace 以及采集侧资源指标。通过/失败均有效，构建失败、捕获失败、判分错误或超时未评分。三题验收完成后，另为同一训练试跑题采集独立的四次 rollout。第一组至少有一个正确和一个错误，最多尝试三组，每题最多一组；不得用 mock、参考补丁或改判分凑出差异。
4. **停服务，再更新。** 完整保存当轮引擎捕获后退出 vLLM，再让本地 Transformers/PEFT 独占同一张卡。更新代码按 rollout 的独立测试分数做组内优势，正确答案可加权重 0.1 的有限工具效率奖励。首版使用 clipped GRPO 目标、等 rollout 权重、无额外 KL 项，冻结基座并做一次 AdamW step，仅保存 LoRA。该同步实现与 HF 双 B200 异步 rollout、权重热更新、原配置 rank 32、原始训练规模均有明确差异。TRL AsyncGRPO 和其双卡示例用于核对契约，未被当作直接单卡共置方案。 [HF 复现报告](https://huggingface.co/blog/harness-adapters-at-scale) · [OpenCode 模型卡](https://huggingface.co/harness-hub/Qwen3.8-27B-opencode-adapted#training)
5. **停训练，再重新加载。** 用同一固定 snapshot 重新启动 vLLM，加载 `adapter_model.safetensors`，用其 SHA-256 前缀生成唯一 LoRA alias。可信启动方核验文件并写 receipt，实际 GET `/v1/models` 必须列出新 alias，一次固定、小预算 canary 请求的结果也必须回报该 alias。旧 alias、基础模型回退、错误的文件摘要或未发生非零更新都停止。单测只验证 receipt 规则，不代表已有服务端证明。
6. **正式对照。** 在 v3 锁定的 12 道留出题上，分别用基础模型和上述 LoRA 各跑一次，使用同一 OpenCode、同一预算与配对 seed。报告 pass@1、配对赢/输数、输出 token、CLI 工具调用、墙钟耗时和设备峰值 VRAM，并单列双方均通过样本的效率。无有效配对的设施问题从正确性指标分开记，最多按相同配置重试一次；仍不完整则不发布正式对照。GPU 指标需由可信主机采集，记录采样周期；训练同时报告框架 allocator 峰值，二者分开。

## 上卡前必须通过的断言

- 捕获来源是可信主机实际导出的 OpenEnv `TrainingTrace`。每次调用核对唯一 `node_id`、引擎自己的 prompt/completion token IDs、每个 completion token 对应的 processed 行为 logprob、覆盖 prompt+completion 的 loss mask。禁止用 CLI 文本重 tokenize。训练前对入选 token 重算行为 logprob 并核对，当前门槛为平均绝对差 ≤0.1、任一点 ≤0.5 nats。若 vLLM 报 eval-only、返回 raw logprobs 或采样设置偏离，停止。
- 提示及作为后续上下文进入的工具输出只提供条件，不作为任何直接 loss target。每个前缀掩码必须为零；保留 completion 中的零位。模型生成的工具调用 token 只有被引擎掩码标记时才进入损失。
- 上下文一旦不再延续上一次引擎 token 前缀，以独立段记录；每段保留 trial ID、node ID 和完整序列摘要。更新对每次调用单独计算 loss，不拼接重写后的序列。缺失或重复调用身份、预算超限、零有效 token 时停止。
- 第一组须有独立正确性差异、有限且非零梯度与 LoRA 参数 L2 变化，基座参数无梯度、未进入优化器且参数版本不变。出现 OOM、设备峰值达到 86 GB、进程未释放 GPU、更新阶段达到 1,200 秒或非有限数均停止。只有更新报告和实际服务 reload receipt 校验通过，才进入留出评测。

## 固定数据计划

目前的 `protocol/dataset-plan-v2.json` 锁定 6 个训练仓库的 72 个候选槽和 4 个完全不同的留出仓库的 24 个槽，记录了源提交与允许的普通功能范围。候选从固定提交制作本地、无网络的小型任务，每题要有原始失败、参考通过、不完整失败三个独立测试对照。用锁定基座在训练候选上每题跑四次，只保留 1–3 次通过的题。留出题不参与筛选、阈值调节或挑选 checkpoint，三道验收题也不进入正式数据。仓库分组、题包 SHA-256、原始上游提交、许可、补丁来源、独立测试和筛选记录随数据版本固定。历史 72/24 计划仍可查阅。当前可复核的小实验集为 [v3 冻结清单](../protocol/first-batch-v3.json) 的 12 道训练候选与 12 道留出候选。 排除任何攻击、漏洞利用、外部目标操作与依赖真实服务或账号的任务。

## 可运行入口和证据格式

```sh
./scripts/run-colab.sh prepare
./scripts/run-colab.sh verify-snapshot /absolute/path/to/verified-snapshot
./scripts/run-colab.sh serve-config /absolute/path/to/verified-snapshot
./scripts/run-colab.sh verify-three /evidence/pilot.json
./scripts/run-colab.sh verify-group /evidence/groups.json
# 只在已获授权且服务已停止的单 G4 上执行
./scripts/run-colab.sh update-once /evidence/pilot.json /evidence/groups.json /snapshot /checkpoint --allow-existing-g4
./scripts/run-colab.sh serve-config /snapshot --checkpoint /checkpoint
./scripts/run-colab.sh verify-reload /checkpoint /evidence/reload.json
./scripts/run-colab.sh compare --manifest-version 3 /checkpoint /evidence/reload.json /evidence/before.json /evidence/after.json
```

`prepare` 执行已有 CPU 验收，并导出 Harbor 格式的三个题包及单独 verifier，在无网络容器直接运行打包后的测试入口。`serve-config` 只打印命令，不启动服务或下载权重。若联调尚无兼容的本地隔离后端，保留 no-network 并停止。当前没有会把所有阶段连起来并自动请求硬件或启动服务的入口。另可在安装 `protocol/colab-schema-requirements.txt` 的独立 Python 环境内运行 `./scripts/run-colab.sh validate-schemas ARTIFACT_DIR/harbor`，核对实际 Harbor/OpenEnv Python 类型。

`pilot.json` 包含 `trials` 列表。v3 的两臂汇总格式见 [配对验收](first-batch-v3.md#基座与-lora-配对报告规范)。`groups.json` 是 `{"groups":[[...]]}`。每条记录由可信侧绑定 `source=openenv_engine`、`model_id`、`model_revision`、`protocol_sha256`、`policy=base|lora`、`opencode_version`、`tool_parser=hermes`、`trial_id`、`task_id`、`verifier=harbor_separate_offline` 和 `correctness`。指标放在 `metrics` 的 `tool_calls`、`model_calls`、`output_tokens`、`peak_vram_bytes`、`elapsed_seconds`。试跑和更新再附 `trace_path` 与 `trace_sha256`，指向同目录原始训练捕获；留出评测附 `repository`、`repo_revision`、`task_sha256`、`seed`，LoRA 臂附 `adapter_sha256`。reload receipt 由可信启动方写入 `loaded_adapter_sha256`、`base_revision`、`advertised_model_ids` 和 `canary_response_model`。这些声明需要可追溯的原始日志支撑，JSON 本身不构成硬件远程认证。

仓库已有固定模型配置、Harbor 题包导出、独立 verifier、文件和轨迹门槛、同步单步更新代码、重载与成对对照检查。正式 Harbor Trial 与隔离 OpenEnv 中继已通过合成引擎的 CPU 联调。**待实测**包括目标 G4 上的 Docker 能力和 vLLM 引擎回执、三个真实工具/判分轨迹、非零 LoRA 更新、服务重载、同题留出对照与显存。[首次 G4 命令与放行条件](g4-smoke-readiness.md#真实三题的命令和放行顺序)

当前云端 CPU 证据：`./scripts/run-colab.sh prepare` 退出 0，13 项测试通过，OpenCode 2.2.7 的原有 9 项对照和 mock 冒烟通过（4 次模拟请求、2 次 CLI 工具调用）。三个新 Harbor verifier 包在无网络 Docker 容器直接运行，原始/参考/不完整各为 `0/1/0`，共 9/9。独立 Python 环境确认 Harbor 0.25.0 接受三个真实任务配置，OpenEnv 0.7.0 接受合成的 typed trace；后一个检查没有调用引擎。原始证据保存在 `artifacts/run-RUN/` 和 `artifacts/colab-prep-RUN/`，未提交产物。
