# 隔离捕获联调与首批任务

CPU 基线为 `bbfac61`。本阶段保留 Qwen3-8B 权重锁和 OpenCode 2.2.7。实际运行的是 OpenCode CLI 和独立测试，模型端点及它提供的引擎字段完全由 fixture 生成。

```sh
./scripts/run-capture.sh
./scripts/run-capture.sh --verify artifacts/relay-cpu-RUN
./scripts/run-first-batch.sh
```

## 中继边界与验收

三个进程分别运行在容器中。OpenCode 和中继只共享一个 `--network none` 的回环网络。上游 fixture 容器没有 TCP 端口，由其与中继共享的临时 Unix socket 收包。任务容器只绑定题目目录和只读 CLI，拿到的是 `dummy`。中继丢弃客户端认证头，只在固定 Unix 上游路由上添加专用一次性合成会话标记。标记文件、socket 和 Docker socket 均未挂载给任务。

同模板隔离探针检查了接口、路由、凭据环境变量名和挂载路径，没打开任何宿主凭据文件，也没有请求外部地址。探针只看到 `lo`，没有非回环路由或可见的会话凭据。独立判分容器仍为 `--network none`，只读取提交文件，参考解和预期值在 Agent 外。

- OpenCode 在边界题完成恰好一次 `read` 和一次 `edit`，修改通过六项独立断言。
- fixture 在 read 的 SSE 中途断流。中继在完整结束标记前不下发任何片段，重试一次，成功后只提交一个请求和节点。同一任务网络中的探针又发出一组字节相同的请求，回放一致且没有第二次上游请求。
- 合成 token 序列把 read 工具结果保留在 edit 的提示中。掩码覆盖提示和生成两段，工具结果位置为零，不是 loss target。最后一回合的合成前缀被改写，分段结果为 `0,0,1`，逐段留有节点 ID 和序列摘要。
- 分别移除引擎 token IDs 和逐 token logprob 时，中继返回 HTTP 502，未重试、未提交、未发送有效响应体。证据带 `source=synthetic_relay` 和 `usable_for_grpo=false`，训练入口实测拒绝。
- 所有原始 CLI 事件、上游与中继日志、合成轨迹、隔离报告、补丁和判分结果写入本地文件。封存记录用 SHA-256 发现文件被改动，未使用签名或远程认证。CPU fixture 按完整请求的规范化 JSON 摘要去重。上真实端点前须改用可信试次和请求标识，避免合并故意重复的调用，并重新核验并发、缓冲上限及真实 OpenEnv 终止语义。

## 首批冻结任务

| 任务 | 分组 | 来源仓库 | 原始／正确／部分 |
| --- | --- | --- | --- |
| `chunked-remainder`：切分和严格尾块 | 训练候选 | `more-itertools/more-itertools` | fail / pass / fail |
| `size-prefix`：文件大小单位和舍入升级 | 训练候选 | `python-humanize/humanize` | fail / pass / fail |
| `elapsed-label`：有符号耗时格式 | 留出候选 | `tqdm/tqdm` | fail / pass / fail |

`protocol/first-batch-v1.json` 锁定 3 个任务、15 个文件摘要、仓库修订和源符号。仓库与整体计划的两组分别匹配且不重叠。题目由本地独立实现，参考固定公开行为，源实现可公开查阅，不声称预训练期盲测。旧的三道试跑题没有混入数据组。训练候选仍待用基座每题四次筛选，留出候选只用于固定评测；以后若改题或扩充，须产生新数据版本。完整的 72/24 槽计划尚未全部制作。

## 真实 G4 之前的依赖和预算预检

1. 先在当前 CPU 跑本页命令和 `./scripts/run-colab.sh prepare`。在装有 `protocol/colab-schema-requirements.txt` 的独立环境中跑 `validate-schemas`，核对 Harbor 0.25.0 和 OpenEnv 0.7.0。记录本地 Docker、Python、OpenCode 和传输组件版本。后续要在真正的 Colab 运行时验证本地 Docker 和独立 verifier 能启动，不能把当前云机的结果当作 Colab 的能力证明。
2. 只在已授权 GPU 上检查 `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv`，要求单个 G4 Blackwell、至少 90 GB 可识别显存。检查已安装 CUDA、PyTorch、vLLM、Transformers、PEFT 解析与版本、同一张卡可用的 BF16。若依赖或运行时不兼容，停止，不替换 GPU 或模型。
3. 用 `./scripts/run-colab.sh verify-snapshot /absolute/path` 校验权重和 tokenizer；用 `serve-config` 查看 `hermes`、关闭 thinking、processed logprobs 和实际 token IDs 的服务参数。可信侧才联通 OpenEnv；任务仍只允许访问本地捕获地址，不继承凭据或服务账号。先证明服务仅本地绑定、任务侧没有公网路由、捕获具备准确的 token/logprob/掩码，并检查改写、重试和节点身份。真实桥接没有完成，默认保持断网。
4. 首次真实 rollout 固定单并发、4,096 上下文、每次最多 512 输出 token、每题最多 2,048 输出 token、12 次调用和 180 秒。达到 86 GB 峰值、OOM、超预算、缺字段或无独立判分均停止。记录设备峰值、采样间隔、输出 token、工具调用和耗时。基座真三题各跑一次，再收集独立四次的有差异奖励组。
5. 停推理释放 GPU，再执行一次 LoRA 更新，之后重启服务核对新适配器摘要和 alias，最终按冻结题目/seed/预算做成对评测。当前只实测 CPU 中继和评分。真实 Harbor/OpenEnv 捕获接线、三题推理、LoRA 更新和重载、G4 显存及耗时均待实测。

## 本次复跑证据

- 中继证据目录为 `artifacts/relay-cpu-RUN/`。真实 CLI 完成 read/edit，独立判分 6/6，通过封存复核。封存清单 SHA-256 为 `ce04eaabfbc09ab67854ad9b1c076bacf8d4bd95300b89d7216384033d7953f1`。
- 首批命令退出 0，九项均符合预期；`artifacts/batch-cpu-RUN/summary.json` 的 SHA-256 为 `08e7f8ca2dc73ae53d7e2dbd2ac105986821befeb7645afcdc7488111efe9a97`。冻结清单 SHA-256 为 `0ab5e5d69598d7aa9c44133d7c014b34c531d6f805c81feef2d45ebf25ac550b`。
- 16 项单元测试通过。基线的 9 项判分、CLI 冒烟和打包 verifier 的 9 项对照均重新通过。原有三题、判分夹具、CPU 协议、G4 模型锁与数据总计划相对 `bbfac61` 没有改动。本次没有 GPU、模型推理、训练、付费服务或推送。
