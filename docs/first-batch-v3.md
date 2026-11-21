# v3 数据冻结和配对验收

## CPU 候选集

[v3 清单](../protocol/first-batch-v3.json) 锁定 12 道训练候选与 12 道留出候选，共 24 个不同仓库身份。清单用 SHA-256 引用 v2，原有 6 道训练题和 4 道留出题完整保留。新增 6 道训练题和 8 道留出题来自独立编写的微型项目快照，仓库标识使用 `oca-fixtures/`，历史题仍使用既有的公开仓库和 Git 修订。云端无法直连 GitHub 获取新的上游修订，本轮采用可离线核验的本地快照。

每道新题的输入快照只有 `TASK.md` 和 `solution.py`。其 `revision` 是 `<文件 SHA-256><两个空格><文件名><LF>` 两行 ASCII 文本的 SHA-256，按上述文件顺序。清单也逐一锁定外部判分用的 `cases.json`、`reference.py` 和 `partial.py`。训练和留出互不共享仓库身份。原有三道启动试题 `boundary`、`parsing`、`serialization` 不进入 v3。

| 划分 | 新增任务 |
| --- | --- |
| 训练 | `ledger-projection`、`compact-release-label`、`daily-wait`、`last-window-index`、`dotted-config-key`、`padded-transpose` |
| 留出 | `capped-wait-series`、`simultaneous-event-rename`、`ranked-encoding-choice`、`wrap-explicit-lines`、`dotted-import-category`、`unique-action-prefix`、`integer-field-issues`、`ordered-subscription-plan` |

```sh
./scripts/run-first-batch.sh --manifest-version 3
```

命令先检查全部文件的散列和仓库划分，再用每个变体各自的临时工作目录和禁网 Docker 容器跑独立判分。预期每题依次得到 `original=fail`、`reference=pass`、`partial=fail`。异常与超时分别记为 `test_error` 和 `test_timeout`。原始样本、补丁和逐用例判分位于该命令打印的 `artifacts/batch-cpu-*/`，汇总文件为 `summary.json`，来源字段为 `cpu_grade_controls`。已有离线验收镜像时，可用 `OCA_OFFLINE_DOCKER_IMAGE_ID=sha256:4bed2b8b523314dbacb1acce4f093ff6a6039a928ed726d74f96df90b165a773` 指定验收所用镜像。

本次云端实际复跑 24 道题。原版 24 项失败、参考修复 24 项通过、部分修复 24 项失败，72 项预期全部命中，其中新增题 42 项。无判分异常或超时。v3 清单 SHA-256 为 `007666b2a193a9ffeb7f077f4df46751dbd03046f38cedd5c8f87a39b3dd9e6d`，本次 `summary.json` SHA-256 为 `89b42a59dcaab92cda9d6f9b538222861cf94e66deab2d0b761a0f5293fa9549`。

## 基座与 LoRA 配对报告规范

评测前用 `./scripts/run-colab.sh compare-plan-v3` 输出冻结的清单与协议摘要、12 个留出任务和固定 seed `314159`。每题的 `task_sha256` 取清单行的 `files` 映射按键排序、紧凑 JSON 编码后计算 SHA-256，对应 `json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")`。两臂各跑一次，均从干净目录开始，使用同一份独立判分。冻结后，留出数据和结果只用于比较。筛题、选适配器和调参均使用训练侧数据。

基座和 LoRA 共用 [G4 协议](../protocol/colab-g4-v1.json) 的模型及权重修订、OpenCode 2.2.7、Harbor/OpenEnv、`hermes` 工具解析器和采样设置。每次尝试最多 180 秒、12 次模型调用、2,048 个生成 token、每次模型调用最多生成 512 个 token，模型上下文上限 4,096。两臂固定同一采样参数和每题 seed。LoRA 臂附实际服务端加载回执与适配器 SHA-256。每条记录附运行 ID、协议摘要、原始证据路径及散列、补丁、Harbor 判分状态、实际模型调用、已完成工具调用、生成 token、耗时和峰值显存。

| 指标 | 报告口径 |
| --- | --- |
| 总体通过率 | 两臂各报 `通过数 / 12`、通过率差（百分点）、LoRA 单独通过题数、基座单独通过题数、两臂都通过和都失败的题数。逐题列出 LoRA 减基座的结果，取值为 −1、0 或 +1。 |
| 配对精确检验 | 双侧精确 McNemar 检验，以单臂通过（结果不一致）的对数做参数为 0.5 的二项检验。没有不一致对时记 `p=1`。只有 12 道固定候选、每题每臂一次，检验能力取决于不一致对数。推断依赖任务对独立及零假设下两臂可交换的假设。 |
| 运行问题 | 缺题、重复、超时、判分错误、身份或预算不符时停止并给出对应错误。全部 12 对可判分才输出正式报告。独立功能测试失败记 0，通过记 1。 |
| 全题成本 | 两臂分别报告输出 token、已完成工具调用和耗时的总数、中位数与题内差值中位数，另报各臂峰值显存。引擎输出总数包含该题的辅助请求。工具调用按状态为 `completed` 的 `tool_use` 计数。 |
| 共同通过题内的成本 | 采用同一批两臂均通过的题，报告题数、两臂成本和逐题差值。该指标受共同成功条件限制。没有共同通过题时填 `null`。 |

正式比较入口读取本地保存的 checkpoint、重载回执及两臂试跑汇总。默认入口仍支持历史计划的 24 个留出槽位。

```sh
./scripts/run-colab.sh compare --manifest-version 3 CHECKPOINT RELOAD.json BASE.json LORA.json
```

两份 v3 汇总的顶层字段为 `source`、`manifest_sha256` 和 `trials`。正式汇总的 `source` 和每条结果的 `source` 均为 `openenv_engine`。每条结果包含计划中对应的题目字段、完整的 `rollout`、`protocol_sha256`、`model_id`、`model_revision`、`opencode_version`、`tool_parser`、`policy`（`base` 或 `lora`）、全局唯一的 `trial_id`、`verifier=harbor_separate_offline`、二值 `correctness`、对应的 `grade_status=pass|fail`、`metrics` 和适配器身份。基座的 `adapter_sha256` 为空，LoRA 的值与已核验的重载回执一致。指标字段为 `output_tokens`、`output_tokens_per_call`、`model_calls`、`tool_calls`、`elapsed_seconds` 和 `peak_vram_bytes`。逐请求生成量必须与调用次数和总生成数一致，并在单次及总预算内。

比较器检查输入汇总、checkpoint 和本地回执的一致性。实际引擎、Harbor 与隔离证据由采集端保存并与试跑 ID 一起审计。v3 的真实采集待完成。

### CPU 模拟复验

```sh
demo="$(mktemp -d)/paired-v3"
PYTHONPATH=harness:. python3 tests/fixtures/paired_v3.py "$demo"
./scripts/run-colab.sh compare --manifest-version 3 --fixture \
  "$demo/checkpoint" "$demo/reload.json" "$demo/base.json" "$demo/lora.json"
```

模拟输入、回执和报告使用 `source=synthetic_fixture`，报告包含 `synthetic=true` 和 `usable_for_grpo=false`。模拟 checkpoint 仅包含测试文本。正式模式会拒绝这批记录。

本次 CPU 模拟覆盖 12 对。基座和 LoRA 分别通过 5 题和 9 题，差值 +33.33 个百分点。6 对结果不一致，双侧精确检验 `p=0.21875`。全题生成量为 2,280 和 2,225 token，工具调用为 42 和 37 次。4 道共同通过题分别为 440 和 400 token，工具调用为 14 和 10 次。模拟报告 SHA-256 为 `86015fc61720dc7ebb3731938e7f00a977b0da3afef277120b3d5c3601244fd8`。同一输入送到正式模式时退出码为 2，报告输出为空。

## 首次有效 GRPO LoRA 更新

先完成真实 `boundary` 单题捕获验收。真实筛题使用训练侧，每道候选从同一基座权重与同一采样配置独立跑四次，记录四次中通过数。首个更新组必须来自同一个预登记任务快照，包含四条不同运行 ID 的真实基座 rollout，分别记录预登记的采样 seed。四条都必须得到 Harbor 独立的 0 或 1，其中至少一个通过、至少一个失败。奖励使用锁定协议的独立正确性和成功样本效率项，组内优势必须有差异。四次全对、四次全错、组内不可评分或缺少捕获时停止该组。现有首步入口仍只接受原三道启动试题。

可信侧校验每个真实引擎的 token ID、按 token 对齐的 processed logprobs 和训练掩码。提示与工具输出不参与 loss，历史重写处分段并保留各段身份。之后只更新 LoRA 参数，记录一次优化器步、有限且非零的 LoRA 参数变化和基础权重冻结证据；重载后核对适配器 SHA-256、所选服务别名与真实 canary 响应。合成联调轨迹和 CPU 控制结果没有 GRPO 数据资格。真实采样、更新与重载仍待实测。
