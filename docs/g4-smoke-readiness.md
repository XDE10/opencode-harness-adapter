# 候选 v2 冻结及真实三题冒烟门槛

本轮从 `4c2c093` 延续。模型仍为 `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`，OpenCode 仍为 2.2.7。已经执行的是 CPU fixture、隔离判分和计划校验。本轮没有真实推理、GPU、训练或升级模型。

## 冻结数据

| 分组 | 题目 | 固定来源仓库 | 部分修复遗漏的例子 |
| --- | --- | --- | --- |
| 训练 | `chunked-remainder` | `more-itertools/more-itertools` | 严格模式仍接受短尾块 |
| 训练 | `optional-choice` | `python-attrs/attrs` | 把布尔值当成整数成员 |
| 训练 | `unicode-unique` | `mahmoud/boltons` | 小写转换漏掉 Unicode 等价 |
| 训练 | `option-summary` | `pallets/click` | 把选项名内斜杠当成前缀 |
| 训练 | `cell-alignment` | `prettytable/prettytable` | 居中时把奇数余量放错侧 |
| 训练 | `size-prefix` | `python-humanize/humanize` | 舍入到进位阈值后没有升单位 |
| 留出 | `locale-case` | `python-babel/babel` | 没有恢复脚本标记的标题大小写 |
| 留出 | `month-clamp` | `dateutil/dateutil` | 二月固定为 28 天 |
| 留出 | `elapsed-label` | `tqdm/tqdm` | 丢掉负亚秒的符号 |
| 留出 | `sorted-interval` | `grantjenks/python-sortedcontainers` | 忽略逆序请求 |

[冻结清单](../protocol/first-batch-v2.json) 包含 10 个互不重复的仓库、固定上游修订、源行为及每题 5 个文件摘要。保留原 v1 清单和三题字节。新增题是本地独立实现的普通功能和数据处理练习，参考公开行为，未复制上游实现；公开来源不等于预训练盲测。四个留出仓库都与训练仓库分离。全计划仍为 72 个训练槽、24 个留出槽，v2 的 24 个留出槽改为四仓库各 6 个。本次只冻结其中 6+4 道候选，未进行真实四次筛题或正式留出评分。

```sh
./scripts/run-first-batch.sh
./scripts/run-first-batch.sh --manifest-version 1   # 可选，复核历史三题
./scripts/run-colab.sh prepare
```

## 真实三题的命令和放行顺序

1. 在 GPU 计时前完成本地 Docker、Python、Harbor 0.25.0、OpenEnv 0.7.0、OpenCode 2.2.7、CUDA/PyTorch/vLLM 兼容性检查。运行 CPU 命令并在装有 `protocol/colab-schema-requirements.txt` 的环境执行 `./scripts/run-colab.sh validate-schemas /path/to/harbor`。镜像、依赖或权重未准备好就停止。仅在已获授权的现有 G4 上，用 `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv` 核对可见单卡、至少 90 GB、BF16 和无竞争进程。[单题冷启动实测和缓存步骤](g4-cold-start.md)
2. 用下面的命令审查固定预算和证据命令。计划中的 `commands.first_g4` 是单题硬件门槛命令。正式三题的 `commands.real_capture` 要等硬件门槛实测通过。

   ```sh
   SNAPSHOT=/absolute/path/to/pinned/local/qwen3-8b
   EVIDENCE=/absolute/path/to/real/evidence/pilot.json
   ./scripts/run-colab.sh smoke-plan "$SNAPSHOT" "$EVIDENCE"
   ./scripts/run-colab.sh verify-snapshot "$SNAPSHOT"
   ./scripts/run-colab.sh serve-config "$SNAPSHOT"
   ```

3. **CPU GO，正式三题 NO-GO。** 正式 Harbor Trial 已在隔离 Docker 环境完成合成引擎验收。可信编排进程需要权限操作本地 Docker daemon，任务和判分容器只使用受限本地挂载。已获授权的现有 G4 上，用下列命令只跑 `boundary` 一次。它校验权重、启动固定的回环 vLLM（`hermes`、thinking off、processed logprobs）、运行 Trial、采集真实引擎 token、掩码及独立二值评分，并停止自己启动的 vLLM。任务模型输出正确或错误均可评分。出现不匹配、超时、漏工具回合或显存触线则停止。预热最多 10 分钟，单题最多 180 秒，容器及 verifier 预留 1 分钟，轮询显存达到 86 GB 时停止。候选产物标为 `g4_engine_candidate` 且 `usable_for_grpo=false`。当前云任务没有执行这条命令。 [OpenEnv Harbor 数据契约](https://huggingface.co/docs/openenv/environments/harbor)

   ```sh
   OCA_UPSTREAM_PYTHON=/abs/harbor-openenv-venv/bin/python \
   OCA_VLLM_BIN=/abs/vllm-venv/bin/vllm \
   ./scripts/run-g4-first-trial.sh /abs/pinned-qwen3-8b /abs/new-first-g4-evidence --allow-existing-g4
   ```

   首跑通过并审查证据后，才放行正式序列 `boundary`、`parsing`、`serialization`。三题需要独立的 `pilot.json`、原始 OpenEnv 轨迹、CLI 工具事件及设备指标。
4. 真实宿主生成 `pilot.json` 后执行 `./scripts/run-colab.sh verify-three "$EVIDENCE" --verify-upstream`。每题要有至少一个工具调用、可信来源、完整模型与协议标识、有效 token/logprob/掩码和独立二值结果。普通功能答错仍可评分；超时、缺证据及基础设施错误不计为答错。最后停止本地推理并保存原始证据。此阶段不触发 LoRA 更新。

## 硬停止与时间预算

| 项目 | 预算或停止条件 |
| --- | --- |
| 本地服务预热 | 最多 10 分钟。未就绪、模型校验不符、运行时不兼容、出现对外路由/凭据即停。 |
| 容器和独立 verifier | 每题预留最多 1 分钟。无法按隔离要求启动或无法独立评分即停。 |
| 三次真实 rollout | 每题 180 秒、12 次模型调用、总输出 2,048 tokens、单请求 512 输出 tokens、上下文 4,096；合计最多 36 次模型调用、6,144 输出 tokens。无自动重试或追加题目。 |
| 引擎与显存 | 峰值达到 86 GB、OOM、超预算、raw 或缺失的行级 logprobs、token/mask 不对齐、身份不符或丢失独立证据即停。生产侧必须在运行中监控，不依赖事后 JSON 校验来限制消耗。 |
| 停服和证据 | 预留 5 分钟。总阶段预算估计为 10 + 3×(1+3) + 5 = 27 分钟，GPU 占用的硬截止为 30 分钟。 |

这是保守的排程区间，前提是权重、镜像和依赖已在本地，真实桥接已放行。不含下载、调试、LoRA 或完整留出评测，没有实测吞吐、显存、用量或价格数据。90 GB 和 86 GB 均为十进制字节门槛。

## 本轮实测证据与恢复

- `artifacts/batch-cpu-RUN/summary.json` 记录 30/30 对照命中。10 道题各自原始失败、正确通过、部分失败，且无测试错误或超时。同目录 `smoke-plan.json` 仅是计划。批次锁 SHA-256 为 `d2133751a60c41be1fc5d3681b79281bd4454101a73a477b061cb4bdea4bb100`。
- 18 项单元测试通过，原有九项判分和九项打包 Harbor verifier 对照通过。实际 OpenCode 的 CPU synthetic 中继复跑且封存复核通过，目录 `artifacts/relay-cpu-RUN/`。这些结果均不属于真实模型验收。
- 可查的 Git 配置无远端，当前云任务未从已发布的来源环境启动，未发现与 `4c2c093` 匹配的持久私有文件或附件。工作区生成的 Git bundle 只是本地恢复包，需要在当前工作区仍可访问时另行下载保存。bundle 恢复方式是 `git clone -b main /path/to/file.bundle restored-repo`。恢复包仅含已提交源码和 Git 历史，不含模型权重、运行产物或本机配置。
