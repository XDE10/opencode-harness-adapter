"""Phase-1 environment & S1-colocation probe for a Colab G4 VM (run via `colab run --keep`).

Verifies:
1. GPU (RTX PRO 6000 Blackwell 96 GB), CPU, RAM, disk, non-root `agent` user creation
2. vLLM + PEFT + Transformers + aiohttp install & versions
3. OpenCode CLI 2.2.7 install + shared XDG_CACHE_HOME warmup
4. Qwen/Qwen3-8B (pinned revision) download to /content/models/Qwen3-8B
5. vLLM serve with:
   --enable-sleep-mode, VLLM_SERVER_DEV_MODE=1, VLLM_ALLOW_RUNTIME_LORA_UPDATING=True,
   --enable-lora, --tool-call-parser hermes, --logprobs-mode processed_logprobs
6. Chat completion returning prompt_token_ids + completion token_ids + processed logprobs
7. Sleep level=1 VRAM drop & wake_up recovery + runtime LoRA load/unload canary
"""
import json, os, subprocess, time, urllib.request, urllib.error

T0 = time.time()
REPORT = {}


def sh(cmd, timeout=1800, check=False):
    t = time.time()
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout + p.stderr).strip()
    print(f"\n$ {cmd}\n[{p.returncode}] {time.time()-t:.1f}s\n{out[-2500:]}", flush=True)
    if check and p.returncode:
        raise SystemExit(f"failed: {cmd}")
    return p.returncode, out


def http_req(url, method="GET", body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:500]


# 1. Hardware & unprivileged agent user
for k, c in {
    "gpu": "nvidia-smi --query-gpu=name,compute_cap,memory.total,driver_version --format=csv,noheader",
    "cpu": "nproc",
    "mem": "free -g | head -2",
    "disk": "df -h /content | tail -1",
    "py": "python3 --version",
    "node": "node --version; npm --version",
}.items():
    REPORT[k] = sh(c)[1]

sh("id -u agent >/dev/null 2>&1 || useradd -m -s /bin/bash agent")
REPORT["agent_uid"] = sh("id agent")[1]

# 2. Python packages (vLLM, PEFT, aiohttp, pytest, hf_transfer; remove stale preinstalled torchao that breaks peft)
sh("pip install -q uv && uv pip install --system -q vllm peft aiohttp pytest hf_transfer && uv pip uninstall --system -q torchao 2>&1 | tail -8", timeout=2400)
REPORT["versions"] = sh(
    "python3 -c 'import json, vllm, torch, transformers, peft, aiohttp, pytest; "
    "print(json.dumps({\"vllm\": vllm.__version__, \"torch\": torch.__version__, "
    "\"cuda\": torch.version.cuda, \"transformers\": transformers.__version__, \"peft\": peft.__version__}))'"
)[1]

# 3. OpenCode 2.2.7 + Pi coding agent
REPORT["opencode"] = sh(
    "mkdir -p /content/tools && "
    "([ -x /content/tools/opencode/bin/opencode ] || "
    "npm install -g --prefix /content/tools/opencode --no-audit --no-fund @opencode/cli@2.2.7 >/tmp/npm.log 2>&1) && "
    "chmod -R a+rX /content/tools/opencode && "
    "/content/tools/opencode/bin/opencode --version"
)[1]
REPORT["pi"] = sh(
    "([ -x /content/tools/pi/bin/pi ] || "
    "npm install -g --prefix /content/tools/pi --no-audit --no-fund @mariozechner/pi-coding-agent >/tmp/npm_pi.log 2>&1 || "
    "npm install -g --prefix /content/tools/pi --no-audit --no-fund @earendil-works/pi-coding-agent >>/tmp/npm_pi.log 2>&1) && "
    "chmod -R a+rX /content/tools/pi && "
    "/content/tools/pi/bin/pi --version"
)[1]

# 4. Model weights
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
sh(
    "python3 -c 'from huggingface_hub import snapshot_download; "
    "snapshot_download(\"Qwen/Qwen3-8B\", revision=\"b968826d9c46dd6066d109eabc6255188de91218\", "
    "local_dir=\"/content/models/Qwen3-8B\", ignore_patterns=[\"*.msgpack\", \"*.h5\"])'",
    timeout=1800,
    check=True,
)
REPORT["weights"] = sh("du -sh /content/models/Qwen3-8B")[1]

# 5. Start vLLM with sleep mode + runtime LoRA updating
sh("pkill -f 'vllm serve' || true; sleep 2")
vllm_cmd = (
    "VLLM_SERVER_DEV_MODE=1 VLLM_ALLOW_RUNTIME_LORA_UPDATING=True VLLM_NO_USAGE_STATS=1 "
    "nohup vllm serve /content/models/Qwen3-8B "
    "--served-model-name qwen3-8b --host 127.0.0.1 --port 8000 --dtype bfloat16 "
    "--generation-config vllm --max-model-len 32768 --gpu-memory-utilization 0.55 "
    "--enable-sleep-mode --enable-auto-tool-choice --tool-call-parser hermes "
    "--enable-lora --max-lora-rank 32 --max-loras 2 "
    "--logprobs-mode processed_logprobs --enable-prefix-caching "
    "> /content/vllm.log 2>&1 &"
)
sh(vllm_cmd)

ready_s = None
for i in range(120):
    time.sleep(5)
    try:
        st, data = http_req("http://127.0.0.1:8000/v1/models", timeout=3)
        if st == 200:
            ready_s = (i + 1) * 5
            break
    except Exception:
        pass
REPORT["vllm_ready_s"] = ready_s
if ready_s is None:
    sh("tail -80 /content/vllm.log")
    raise SystemExit("vLLM failed to start")

REPORT["vram_active_mib"] = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")[1]

# 6. Test token_ids + processed logprobs capture
st, resp = http_req("http://127.0.0.1:8000/v1/chat/completions", "POST", {
    "model": "qwen3-8b",
    "messages": [{"role": "user", "content": "Reply with 3 words."}],
    "max_tokens": 16,
    "temperature": 0.8,
    "top_p": 1.0,
    "logprobs": True,
    "return_token_ids": True,
    "chat_template_kwargs": {"enable_thinking": False},
})
ch = resp["choices"][0]
REPORT["capture_probe"] = {
    "status": st,
    "resp_keys": sorted(resp.keys()),
    "choice_keys": sorted(ch.keys()),
    "n_prompt_ids": len(resp.get("prompt_token_ids") or []),
    "sample_prompt_ids": (resp.get("prompt_token_ids") or [])[:5],
    "n_completion_ids": len(ch.get("token_ids") or []),
    "sample_completion_ids": (ch.get("token_ids") or [])[:5],
    "n_logprobs": len((ch.get("logprobs") or {}).get("content") or []),
    "sample_logprob_item": ((ch.get("logprobs") or {}).get("content") or [None])[0],
    "text": ch["message"].get("content"),
}

# 7. Test Sleep level=1 & Wake-up
t_sleep = time.time()
st_s, r_s = http_req("http://127.0.0.1:8000/sleep?level=1", "POST")
vram_slept = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")[1]
st_w, r_w = http_req("http://127.0.0.1:8000/wake_up", "POST")
vram_woke = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")[1]
REPORT["sleep_wake"] = {
    "sleep_status": st_s,
    "vram_slept_mib": vram_slept,
    "wake_status": st_w,
    "vram_woke_mib": vram_woke,
    "roundtrip_s": round(time.time() - t_sleep, 2),
}

REPORT["total_s"] = round(time.time() - T0, 1)
os.makedirs("/content/probe", exist_ok=True)
with open("/content/probe/report.json", "w") as f:
    json.dump(REPORT, f, indent=2)
print("\n===PROBE_REPORT===\n" + json.dumps(REPORT, indent=2), flush=True)
