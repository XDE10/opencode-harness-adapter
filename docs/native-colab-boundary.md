# 独立 G4 的 Boundary 单题启动包

首选输入是原生授权通道预置到独立 VM 本地磁盘的私有 Drive 缓存。启动包只含源码、启动器和校验清单。G4 模式读取本地目录、拒绝直接使用 Drive/FUSE 等网络挂载，并且只使用本地 wheel、权重和镜像。不要传入 Drive 凭据。

## 缓存布局

```text
oca-boundary-cache/
  snapshot/                 锁定 Qwen3-8B 的 10 个文件
  harbor-wheels/            Python 3.13 的 144 个 wheel
  vllm-cu129-wheels/        Python 3.12 的 196 个 wheel
  flashinfer-wheels/        CUDA 12.9 的 3 个 wheel，含 SM120f
  tools/                    两套 Python 和官方 OpenCode CLI 平台包
  image/docker-image.tar    Docker 29.9.2 对锁定镜像的 linux/amd64 导出
```

| 路径 | 件数 | 字节 |
| --- | ---: | ---: |
| `snapshot/` | 10 | 16,392,983,007 |
| `harbor-wheels/` | 144 | 169,910,341 |
| `vllm-cu129-wheels/` | 196 | 5,560,693,613 |
| `flashinfer-wheels/` | 3 | 1,754,269,502 |
| `tools/` | 3 | 266,523,741 |
| `image/` | 1 | 121,579,008 |
| **合计** | **357** | **24,265,959,212** |

`cache-manifest.json` 列出每个路径的精确字节数、SHA-256 和公开来源，`CACHE.SHA256SUMS` 可在缓存根目录用 `sha256sum -c /path/to/CACHE.SHA256SUMS` 复核。Docker 的官方镜像引用、导出 SHA-256 与加载后必须出现的具体 linux/amd64 image ID 都已锁定。不同 Docker 导出格式若产生其他字节，启动器会拒绝。

## 原生调度入口

以下命令交给已有授权的原生 Colab CLI，并指向**已分配且专用于本试跑的**会话。`SESSION` 由原生管理方提供。缓存须已在该 VM 的本地盘上可读，其中不存在 Drive 挂载。G4 启动时还要求工作盘在缓存之外有至少 **22 GB** 空闲。原生调度从分配时刻起计时。

```sh
colab upload -s "$SESSION" oca-colab-boundary.py /content/oca-colab-boundary.py
colab ssh -s "$SESSION" -- python3 /content/oca-colab-boundary.py \
  --allow-existing-g4 --cache /content/oca-boundary-cache --output /content/oca-boundary-evidence
```

启动器为单个 Python 文件，也兼容原生 CLI 的单文件执行语义。设备、驱动、磁盘、Docker、镜像及无网容器探针都是硬门槛。只有命中缓存并校验通过、离线依赖安装成功后，才会创建短暂 BF16 CUDA 验证和运行一次 `boundary`。产物位于新建的输出目录，`stop.json` 记录提前停止的门槛。成功产物至少包括 `trial/summary.json`、`trial/final.patch`、`trial/openenv-candidate-trace.json` 和 Harbor 结果目录。可以让已授权的原生端打包这个证据目录，以 `colab download -s "$SESSION" REMOTE LOCAL` 取回。随后用 `colab stop -s "$SESSION"` 释放该会话并用 `colab sessions` 确认。控制端须设置从分配到释放的 30 分钟硬截止，并给故障时的释放操作留时间。 [Google Colab CLI 命令索引](https://github.com/googlecolab/google-colab-cli)

| 时间窗 | 范围 |
| --- | --- |
| 8 分钟 | 本地预检、校验、隔离探针和离线安装，超时即停 |
| 15 分钟 | vLLM 预热最多 10 分钟、Trial 和判分最多 4 分钟，其余留给本地进程收尾 |
| 5 分钟 | 取证、停止并确认云端会话释放 |
| 2 分钟 | 额外调度余量，默认要求缓存已在本地 |

如果只能从公网获得文件，优先在**未开卡的 CPU 环境**准备同样的缓存。原生端可把已校验的目录同步到私有 Drive 或预置本地盘。CPU 命令要求 Docker 本地已缓存清单中的官方镜像，会在发起公网下载前校验镜像导出和隔离探针。下载从最大文件开始，最多 12 路并行，按 45 秒观测速率，估算余量不足会中止，`.part` 文件可供续传。整个准备窗口为 8 分钟。单算 24.14 GB 的公开文件，即使完全用满 8 分钟也需要约 402 Mbit/s，实际还要分给隔离检查和哈希。目标已有缓存时，可直接使用只读公网侧检查关闭的 `--verify-cache`。

```sh
python3 oca-colab-boundary.py --prepare-public-cache --cache /local/staging/oca-boundary-cache
python3 oca-colab-boundary.py --verify-cache --cache /local/staging/oca-boundary-cache
```

若原生托管 VM 不能提供已有本地缓存、Docker 运行权限或隔离探针通不过，该环境为 NO-GO。空白 G4 的公网下载不在启动路径中，也没有训练入口。

## CPU 验收记录

当前云工作区已校验 357 个文件，耗时约 10.4 秒。使用同一缓存里的 OpenCode、Python 3.13 与 144 个 wheel 离线重建后，正式 Harbor CPU Trial 的原稿为 0，补丁为 1，OpenEnv 导出了 3 个合成回合。更严格的目标启动探针实测发现，当前云工作区的容器读到的 cgroup 上限为 16 GiB、PID 无限、CPU 4 核，未达到本包要求的 192 MiB、32 PID 和 0.5 核，所以完整启动器会在隔离门槛停止。目标 G4 是否达标仍须由原生端检查。[CUDA 12.9 驱动说明](https://docs.nvidia.com/cuda/archive/12.9.0/cuda-toolkit-release-notes/index.html)
