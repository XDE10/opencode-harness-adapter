# Harbor / OpenEnv 的隔离 CPU 接线

本阶段以 `2c44214` 为基线，模型锁及冻结题不变。验收范围固定为 `boundary` 一题，OpenCode 2.2.7 完成读文件和修改边界条件，OpenEnv 0.7.0 导出结构化轨迹，Harbor 0.25.0 对原稿和补丁分别给出独立结果。成功后也停止，不进入真实推理或训练。 [OpenEnv Harbor 契约](https://huggingface.co/docs/openenv/environments/harbor) · [Harbor 独立 verifier](https://docs.harborframework.com/tasks/separate-verifier)

## 运行

需要已在本地缓存的 CPU Docker 镜像、OpenCode 和匹配镜像的 Python 3.13 环境。该环境需事先安装 `protocol/colab-schema-requirements.txt`（本次用的是已备好的环境）。这条命令不会安装依赖、拉镜像、下载模型或访问外部推理服务。

```sh
OCA_UPSTREAM_PYTHON=/absolute/path/to/venv/bin/python ./scripts/run-harbor-openenv-cpu.sh
```

### 实际接线与执行

1. Harbor 0.25.0 通过公开的 `Trial.create()` 和 `Trial.run()` 调度一次正式 Trial。自定义 `BaseEnvironment` 使用预缓存 Docker 镜像，创建全新的任务容器。OpenCode 在容器内的 tmpfs 修改题目，Harbor 将唯一的有界普通文件 `/work/solution.py` 记录到 artifact manifest，停止任务容器，然后把文件交给另一断网容器。独立的 `Verifier.verify()` 读取只读测试和提交，并保存 `reward.json`。原稿在单独容器运行同一判分器作为对照。 [Harbor 自定义 sandbox](https://docs.harborframework.com/sandboxes/custom-sandboxes)
2. 任务端通过仅回环的 HTTP shim 请求 `/v1/chat/completions`。shim 只连专用 Unix socket。可信容器运行真实的 OpenEnv `create_app`，注册会话，注入仅本轮的内部会话标记，调用真实捕获代理并从 `trace_entries` 导出，经 `TrainingTrace.from_entries` 验证。捕获和模拟引擎同在断网容器内，彼此只使用回环。记录只保存 token 字段、损失掩码、节点和计数，不保存内部标记或原始聊天正文。
3. 探针在实际的任务和判分容器内确认只有 `lo`，没有非回环路由、私有挂载、宿主凭据环境变量或 Docker socket。任务可以读取模型列表，`/health`、`GET /sessions` 和 `POST /sessions` 返回 404。任务只用无权限的 `dummy`。宿主编排以最小环境运行，测试进程通过 Python 审计钩子拒绝 IP socket 与域名解析，并使用固定的本地 Docker Unix socket。容器网络隔离由 Docker 执行。
4. 通过条件是一次实际 `read` 和一次实际 `edit`，OpenEnv 导出读、编辑、结束三个回合，工具结果在提示段且掩码为零，原稿得 0、补丁得 1。训练消费者必须拒绝导出文件。组件版本、隔离、轨迹或分数不符合就停止。OpenCode 调用预算为 45 秒，OpenEnv 最多六次请求，不自动启动其他题；临时容器退出时清理。
5. 引擎 HTTP 转发在训练轨迹过滤之前结算每次请求，因而也计入 OpenCode 的标题请求。每次请求的上限取单次上限、请求上限和本轮剩余量的最小值。引擎返回的 completion token IDs 数量必须与 usage 一致，缺失或超限会停止该轮，未知用量的失败也不重试。CPU 联调用每次最多 3、本轮最多 6 个合成 token 的小预算，核对引擎实际收到的上限，并检查耗尽后的追加请求在转发前收到 HTTP 422。生产预算仍由实验协议锁定，真实 vLLM 的 usage 与 token IDs 一致性仍需实测。

### 受控范围

模型回复、工具选择和引擎响应里的 token IDs/logprobs 来自脚本，而非 GPU 模型。OpenEnv 的采集、校验及掩码组装是实际运行的实现；Harbor 的 verifier 和 OpenCode 工具执行也是真实的。结果显式标成 `source=openenv_capture_synthetic_backend`、`usable_for_grpo=false`。此前自研模拟中继的重试／断流用例另跑，本次不将它们归功于 OpenEnv。

### 首次真机仍需通过

- 目标 G4 上确认 CUDA、BF16 与本地 Docker 隔离能力。首跑复用已通过 CPU 验收的正式 Harbor Trial、自定义 Docker sandbox 和 Unix 中继，增加实际 vLLM 引擎。
- 在授权的本地 vLLM 端点打通固定 Qwen3-8B、`hermes`、非 thinking 和 processed logprobs。用真实引擎回执核 token 对齐、工具上下文掩码、改写和异常流；确认生产链路的超时、输出与调用上限、终止和显存监控。CPU 测试中的 SSE shim 会缓冲有界响应，生产流行为仍需验收。
- 按 [真实三题门槛](g4-smoke-readiness.md) 得到三题原始轨迹与独立评分。之后才验证一次非零 LoRA 更新、服务重载与配对留出；本轮这些均未执行。

## 实测证据

早期 `Verifier.verify()` 直接调用的证据在 `artifacts/harbor-openenv-cpu-RUN/`。OpenCode 完成 read/edit，OpenEnv 导出三个回合，Harbor 原稿的可见断言为 4/6（独立奖励 0），修改后 6/6（奖励 1），训练入口拒绝合成来源。原始运行产物保留在忽略目录。

`bc2099e` 之后的预算检查复跑见 `artifacts/harbor-openenv-cpu-RUN/summary.json`，SHA-256 为 `3eb91bf9c813b9c13c0280f02e6e30e60c9ca74646446fd5a04bfebdee83297e`。引擎实际收到的单次上限依次为 `3, 3, 3, 1`，共返回 6 个合成 token，追加请求收到 HTTP 422。三个轨迹回合、两个工具调用和 0/1 独立评分均复验通过。21 项单元测试通过，其中预算用例覆盖固定的 2,048 总上限、调用次数以及缺失、不匹配和超限的引擎计数。

正式 Trial 的 CPU 复跑在 `artifacts/harbor-openenv-cpu-RUN/`。摘要 SHA-256 为 `106892114e7906df789ed44b9fd4c9eb1192770480c008bc3b6134514fb127bb`。Harbor artifact manifest 确认收取 `/work/solution.py`，独立 reward 为 1，原稿对照为 0。两侧隔离探针、实际 CLI read/edit、三个 OpenEnv 回合、预算拒绝和训练入口拒绝合成来源均通过。22 项单元测试通过。
