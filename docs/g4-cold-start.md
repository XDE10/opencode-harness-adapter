# 单题 G4 的开卡前准备

模型固定为 `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`。从公开的指定修订缓存 10 个文件，共 16,392,983,007 字节。Hugging Face tree API 提供精确长度及五个分片的 LFS SHA-256。仓库分别保存 [长度清单](../protocol/qwen3-8b-public-sizes.json) 和 [SHA-256 锁](../protocol/colab-g4-v1.json)。[官方模型修订](https://huggingface.co/Qwen/Qwen3-8B/tree/b968826d9c46dd6066d109eabc6255188de91218)

```sh
CACHE=/abs/cold-cache
python3 -m colab.prefetch
python3 -m colab.prefetch "$CACHE/snapshot"
./scripts/run-colab.sh verify-snapshot "$CACHE/snapshot"
```

`colab.prefetch` 只取锁定文件，先检查磁盘，保留可续传的 `.part`，完整文件通过长度和 SHA-256 校验后才进入快照。当前 Codex 工作区缓存位于 `.tools/g4-cold-start/`。它不随 Git bundle，也不自动出现在独立 G4。

## 开卡前在目标镜像或同配置 CPU 环境核对

1. 安装 OpenCode 2.2.7 与 Python 3.13 下的 Harbor 0.25.0、OpenEnv 0.7.0 和 FastMCP 3.4.11。用锁定的 Docker 镜像在本地 daemon 上运行完整 CPU Trial。该验收覆盖正式 Harbor 调度、唯一 artifact 传递和独立判分。CPU 环境的实际检查不替代 G4 主机启动时的 Docker 和驱动检查。

   ```sh
   ./scripts/install-opencode.sh
   OCA_UPSTREAM_PYTHON=/abs/harbor-openenv-venv/bin/python ./scripts/run-harbor-openenv-cpu.sh
   ```

2. 可信编排进程访问本机 Docker Unix socket，宿主运行只绑定 `127.0.0.1` 的 vLLM。宿主 OpenEnv 从专用 Unix socket 接任务中继。只读挂载该 socket 给独立的 `--network none` shim，非 root 任务仅共享 shim 的回环网络。任务只用自己的临时工作区，判分容器另起，按 Harbor manifest 接收有界普通文件与只读独立测试。任务和 verifier 都没有 Docker socket、权重挂载或凭据。当前工作区已在 CPU 上实际验证这个宿主 socket 拓扑。若目标 G4 的提供方运行时缺少可用 Docker、挂载、用户或断网能力，保持 NO-GO。 [Docker none 网络](https://docs.docker.com/engine/network/drivers/none/) · [Harbor 自定义 sandbox](https://docs.harborframework.com/sandboxes/custom-sandboxes)
3. 在独立 Python 环境为目标驱动备好 vLLM、配套 PyTorch 与匹配版本的 FlashInfer 内核。此机预取的候选为 Linux x86-64、Python 3.12、glibc 2.35 或更新，`vllm==0.32.0+cu129`、`torch==2.13.0+cu129` 和 `flashinfer-python==0.7.0.post1`。NVIDIA 将 RTX PRO 6000 Blackwell 标为计算能力 12.0。确认目标主机采用兼容驱动、单卡可见、BF16 可用，而且内核缓存可离线使用。wheel 解包和依赖解析只能检查软件分发，实际 CUDA kernel、工具解析、引擎回执及显存须在 G4 验收。 [vLLM GPU 安装](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/) · [FlashInfer 安装](https://docs.flashinfer.ai/installation.html) · [NVIDIA 计算能力](https://developer.nvidia.com/cuda/gpus)

## 已验证的本地缓存

| 内容 | 件数 | 压缩或源文件字节数 | 验证 |
| --- | ---: | ---: | --- |
| 锁定模型快照 | 10 | 16,392,983,007 | 每件长度和固定 SHA-256，随后完整复核 |
| Harbor CPU wheel | 144 | 169,910,341 | SHA-256、离线安装、依赖一致性和正式 CPU Trial |
| vLLM CUDA 12.9 wheel | 196 | 5,560,693,613 | 哈希锁、仅本地 wheel 的离线安装解析 |
| FlashInfer cubin、shim 和 SM120f provider | 3 | 1,754,269,502 | 上游 release 摘要、仅本地 wheel 的离线安装解析 |

同时保留 wheel 并解包环境时，模型与这些包合计约 42.8 GB，预留至少 45 GB，再为 Docker 镜像和运行临时文件保留余量。此机剩余空间只支持保留已验证的 GPU wheel；GPU 环境的安装和启动尚未实测。

目标主机能访问相同缓存时，在本地离线安装候选软件。FlashInfer 最后一步选取 G4 的 `sm120f` provider，等同于该版本官方安装器的 minimal 模式。其他 GPU 架构的 provider 不在缓存里。

```sh
(cd "$CACHE/harbor-wheels" && sha256sum -c SHA256SUMS)
uv --offline pip install --python /abs/harbor-openenv-venv/bin/python --no-index \
  --find-links "$CACHE/harbor-wheels" -r "$CACHE/harbor-cpu-resolved.txt"
(cd "$CACHE/vllm-cu129-wheels" && sha256sum -c SHA256SUMS)
(cd "$CACHE/flashinfer-wheels" && sha256sum -c SHA256SUMS)
/abs/vllm-venv/bin/python -m pip install --no-index --require-hashes \
  --find-links "$CACHE/vllm-cu129-wheels" -r "$CACHE/vllm-cu129-resolved.txt"
/abs/vllm-venv/bin/python -m pip install --no-index --no-deps \
  --find-links "$CACHE/flashinfer-wheels" 'flashinfer-cubin==0.7.0.post1' \
  'flashinfer-jit-cache==0.7.0.post1+cu129' 'flashinfer-jit-cache-sm120f==0.7.0.post1+cu129'
```

## 30 分钟门槛

- **目标已预热依赖和缓存时有条件可行。** 本次权重并行下载及逐件校验约 268 秒，整体 SHA-256 复核约 18 秒。单题规划取 10 分钟 vLLM 预热、4 分钟 Trial 和判分、5 分钟保存证据及停止服务和释放，合计约 19 分钟，另外约 11 分钟留给分配、最终预检和变化。推理硬停仍是每题 180 秒、最多 12 次调用和 2,048 个输出 token，显存达到 86 GB 即停。墙钟从提供方分配开始算，30 分钟前由独立运行时控制端确认释放。
- **空白 G4 当前 NO-GO。** 权重与上述公开包共约 23.88 GB，以 100 Mbit/s 下载的理想时间约 31 分 50 秒。只用余下 11 分钟下载会要求持续约 289 Mbit/s，还需另留镜像、解包和安装时间。当前 Codex 下载测速无法证明新 G4 可读相同缓存或达到相同速度。只在目标缓存可访问、CPU 隔离通过、且独立运行时释放通道可用时才按 30 分钟窗口开卡。首跑命令见 [G4 单题入口](g4-smoke-readiness.md#真实三题的命令和放行顺序)。
