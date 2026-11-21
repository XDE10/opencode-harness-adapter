# OpenCode Harness Adapter

在一张 Colab G4 96 GB 上复现 OpenCode Harness Adapter 的核心流程。基座固定为官方 `Qwen/Qwen3-8B` 的 `b968826d9c46dd6066d109eabc6255188de91218`，OpenCode 固定为 `@opencode/cli@2.2.7`。实验用三道冒烟题和 12 道训练、12 道按仓库隔离的留出候选，覆盖普通 Python 功能、数据处理和测试。

## CPU 复现

需要 Linux、Python 3.11+、Docker 本地 Unix socket，以及 Node.js/npm 或已经缓存的锁定 OpenCode。运行以下一条命令即可跑单元测试、CLI 版本与帮助检查、三题的九项独立判分对照，以及一次真实 OpenCode 的合成后端冒烟。

```sh
./scripts/run-harness.sh
```

没有缓存时，安装步骤访问公开 npm registry 和锁定的 Docker 镜像发行源。已有缓存时可设置 `OPENCODE_PREFIX`，并用本地锁定镜像 ID 环境变量 `OCA_OFFLINE_DOCKER_IMAGE_ID` 避免拉取。任务和判分在隔离 Docker 容器中运行，判分使用独立测试。每次运行的报告写到忽略目录 `artifacts/`。历史合成轨迹与原始运行记录保留在执行环境中。

如需复核全部 24 道候选的原版、参考和部分修复，用 `./scripts/run-first-batch.sh --manifest-version 3`。如需复核 OpenEnv 捕获或配对比较器，用 [Harbor CPU 联调](docs/harbor-openenv-cpu.md) 和 [v3 模拟复验](docs/first-batch-v3.md#cpu-模拟复验)。

## 单卡配置

| 项目 | 锁定值 |
| --- | --- |
| 工具与捕获 | OpenCode 2.2.7、OpenEnv 0.7.0、Harbor 0.25.0 |
| 推理 | vLLM BF16，`hermes` 工具解析，关闭 thinking，温度 0.8，top-p 1.0 |
| 每题预算 | 上下文 4,096，单次生成 512，本题生成合计 2,048，最多 12 次模型调用和 180 秒 |
| 更新 | 同一训练题四次真实采样，有成功也有失败时才验收一步 LoRA GRPO；rank 16、alpha 32，冻结基座 |
| 留出 | 同题、同 seed、同预算配对；比较通过率、生成 token、工具调用、耗时及峰值显存 |

配置以 [单卡协议](protocol/colab-g4-v1.json) 为准。单卡按顺序收集、更新、重新加载 LoRA，再执行配对比较。首轮先按 [单题预检](docs/native-colab-boundary.md) 验收 `boundary` 的真实工具调用、引擎 token IDs、processed logprobs、训练掩码与 Harbor 独立评分。

## 验证边界

CPU 已验证独立判分、OpenCode 工具循环、合成后端的真实 OpenEnv 捕获与 Harbor 判分、冻结清单及 v3 比较器。合成 trace 标记为不可训练。严格启动探针在当前 CPU 复验环境没有观察到要求的有效 cgroup 限额。目标单卡上的正式真实试跑、非零更新、LoRA 重载和 12 对真实比较均待验收。

[完整单卡流程](docs/colab-g4.md) · [上游版本、逐文件溯源与许可](docs/upstream.md) · [第三方声明](NOTICE)
