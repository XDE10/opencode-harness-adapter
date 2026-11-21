# CPU 暂存到授权的私有存储

暂存入口为 `python3 -m colab.stage_drive`。它使用 `497c800` 启动包对应的 357 项缓存清单，共 24,265,959,212 字节。已存在的本地缓存可直接使用。需要补下载时只允许清单中的公开源。CUDA、vLLM 和项目的其他会话都不参与这个 CPU 阶段。[精确文件清单](../protocol/native-colab-cache.json)

## 原生调度端提供的证明

使用已有授权在云端分别挂载同一私有存储的写视图和只读视图。只读视图应是独立、无写入缓存的提供方回读，不能是写挂载的 bind 别名。调度端从已授权的提供方核实两个根目录的 ID、稳定属主 ID、剩余字节及私有权限。`OpenCodeCache` 若已存在，也须是属主私有目录。把这些核验结果写成下面的本地证明文件。

先获取两个挂载的绑定信息。这两个命令只检查云端 Linux 挂载表。

```sh
python3 -m colab.stage_drive --describe-mount /mnt/example-write
python3 -m colab.stage_drive --describe-mount /mnt/example-readback
```

证明文件只包含元数据。下面的 `write_mount` 和 `read_mount` 应替换成完整的命令输出，剩余空间应填写已核实的整数。用于 `--expected-owner` 的 存储身份应来自已知的授权配置。

```json
{
  "schema_version": 1,
  "owner_id": "<已从提供方核实的 存储稳定属主 ID>",
  "private": true,
  "drive_root_id": "<写挂载对应的提供方根 ID>",
  "read_drive_root_id": "<只读挂载对应的同一提供方根 ID>",
  "uncached_readback": true,
  "available_bytes": 0,
  "write_mount": {},
  "read_mount": {}
}
```

脚本核对证明和当前挂载信息。提供方属主鉴别与权限检查由原生调度端完成。脚本绑定两个打开的挂载描述符，在写入和提交前重复检查挂载身份。

## 暂存命令

```sh
python3 -m colab.stage_drive \
  --write-mount /mnt/example-write --read-mount /mnt/example-readback \
  --owner-proof /tmp/example-owner-proof.json --expected-owner "$VERIFIED_OWNER_ID" \
  --local-cache /cloud/local/oca-boundary-cache --fetch-public
```

`--local-cache` 指向云端本地磁盘，可跨同一台 CPU 工作机的重试复用。现成缓存已完整时省略 `--fetch-public`。公网断点保留在本地 `.part`，按字节续传后用锁定 SHA-256 校验。下载进程不继承 HTTP 代理或服务账号变量，需要云 CPU 的公开 HTTPS 直连。需要重新生成 Docker 导出时，CPU 主机须事先有已锁定的公开镜像，导出字节必须吻合。

暂存使用文件级续传。完整文件经独立只读视图复核后可复用。中断的远端临时文件不计为完成。已存在但校验错误的最终文件会触发停止。每次由一个调度端暂存同一版本。目录格式为 `OpenCodeCache/qwen3-8b-<修订>-497c800-<清单摘要>`。全部 357 项回读校验结束后才提交 `READY`，并从只读视图回读标记。重复执行会复核已就绪目录。

## 单题的下一关

原生端收到已回读的 `READY` 后，将同一版本的完整目录云端直拷到独立 G4 的 VM 本地盘，按启动包清单重新验哈希。G4 启动器仍会核对设备、空闲空间、Docker 和有效隔离。只有通过这些检查才运行 `boundary` 一题，30 分钟窗口从原生端分配算到释放。首轮证据必须包含真实引擎 token IDs、对齐的 logprobs 和掩码、实际工具事件与 Harbor 独立评分。[单题启动器和释放要求](native-colab-boundary.md)
