"""Phase-1 environment, sandbox, causal-conv1d & DeltaNet vLLM LoRA probe for a Colab G4 VM.

Verifies:
1. GPU (RTX PRO 6000 Blackwell 96 GB), CPU, RAM, disk, non-root `agent` user, `bubblewrap` availability
2. vLLM + PEFT + Transformers + aiohttp + datasets + flash-linear-attention + causal-conv1d
3. OpenCode 2.2.7 + Pi CLI install
4. Qwen/Qwen3.5-9B download to /content/models/qwen35-9b
5. vLLM serve with --enable-sleep-mode, --enable-lora, --max-lora-rank 64 (for lossless rank-2r Super-Adapter!)
6. Chat completion returning prompt_token_ids + completion token_ids + processed logprobs
7. Sleep level=1 VRAM drop & wake_up recovery
8. Qwen3.5 Gated DeltaNet LoRA Canary (`in_proj_qkv, in_proj_z, in_proj_b, in_proj_a, out_proj`) ->
   records `deltanet_lora_supported: true|false` so Phase 2 automatically chooses safe target_modules!
"""
import json, os, shutil, subprocess, tempfile, time, urllib.request, urllib.error

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


# 1. Hardware, unprivileged agent user & bubblewrap sandbox check
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

# Try installing bubblewrap for mount/PID/IPC sandboxing; probe whether container kernel permits userns
sh("which bwrap >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq bubblewrap >/dev/null 2>&1) || true", timeout=180)
rc_bw, _ = sh("bwrap --ro-bind / / --proc /proc --dev /dev --unshare-pid --die-with-parent /bin/true 2>&1", timeout=15)
REPORT["bwrap_available"] = (rc_bw == 0)

# 2. Python packages (+ datasets + optional prebuilt causal-conv1d wheel for DeltaNet speedup)
sh("pip install -q uv && uv pip install --system -q vllm peft aiohttp pytest datasets flash-linear-attention hf_transfer && uv pip uninstall --system -q torchao 2>&1 | tail -8", timeout=2400)
# Attempt prebuilt wheel only (no 20-min source compile); falls back cleanly if unavailable
rc_cc, _ = sh("uv pip install --system --only-binary=:all: -q causal-conv1d 2>&1 | tail -8 || true", timeout=180)
REPORT["causal_conv1d_installed"] = (sh("python3 -c 'import causal_conv1d; print(causal_conv1d.__version__)'")[0] == 0)
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

# 4. Model weights (Qwen/Qwen3.5-9B)
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
sh(
    "python3 -c 'from huggingface_hub import snapshot_download; "
    "snapshot_download(\"Qwen/Qwen3.5-9B\", "
    "local_dir=\"/content/models/qwen35-9b\", ignore_patterns=[\"*.msgpack\", \"*.h5\"])'",
    timeout=1800,
    check=True,
)
REPORT["weights"] = sh("du -sh /content/models/qwen35-9b")[1]

# 5. Start vLLM with sleep mode + runtime LoRA updating (max-lora-rank 64 for lossless rank-2r Super-Adapter!)
sh("pkill -9 -f 'VLLM|vllm' || true; sleep 2")
vllm_cmd = (
    "VLLM_SERVER_DEV_MODE=1 VLLM_ALLOW_RUNTIME_LORA_UPDATING=True VLLM_NO_USAGE_STATS=1 "
    "nohup vllm serve /content/models/qwen35-9b "
    "--served-model-name qwen35-9b --host 127.0.0.1 --port 8000 --dtype bfloat16 "
    "--generation-config vllm --max-model-len 32768 --gpu-memory-utilization 0.58 "
    "--enable-sleep-mode --enable-auto-tool-choice --tool-call-parser qwen3_coder "
    "--enable-lora --max-lora-rank 64 --max-loras 2 "
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
    "model": "qwen35-9b",
    "messages": [{"role": "user", "content": "Reply with 3 words."}],
    "max_tokens": 16, "temperature": 0.8, "top_p": 1.0,
    "logprobs": True, "return_token_ids": True,
    "chat_template_kwargs": {"enable_thinking": False},
})
ch = resp["choices"][0]
REPORT["capture_probe"] = {
    "status": st,
    "n_prompt_ids": len(resp.get("prompt_token_ids") or []),
    "n_completion_ids": len(ch.get("token_ids") or []),
    "n_logprobs": len((ch.get("logprobs") or {}).get("content") or []),
    "text": ch["message"].get("content"),
}

# 7. Test Sleep level=1 & Wake-up
t_sleep = time.time()
st_s, _ = http_req("http://127.0.0.1:8000/sleep?level=1", "POST")
vram_slept = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")[1]
st_w, _ = http_req("http://127.0.0.1:8000/wake_up", "POST")
vram_woke = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")[1]
REPORT["sleep_wake"] = {
    "sleep_status": st_s, "vram_slept_mib": vram_slept,
    "wake_status": st_w, "vram_woke_mib": vram_woke,
    "roundtrip_s": round(time.time() - t_sleep, 2),
}

# 8. Canary test: Does vLLM runtime LoRA accept Qwen3.5 Gated DeltaNet targets?
canary_dir = tempfile.mkdtemp(prefix="oca-deltanet-canary-")
try:
    http_req("http://127.0.0.1:8000/sleep?level=1", "POST")
    probe_py = (
        "import json, torch\n"
        "from peft import LoraConfig, get_peft_model\n"
        "from transformers import AutoModelForCausalLM\n"
        "base = AutoModelForCausalLM.from_pretrained('/content/models/qwen35-9b', local_files_only=True, dtype=torch.bfloat16, device_map='cpu')\n"
        "l0_lins = sorted({n.split('.')[-1] for n, m in base.named_modules() if isinstance(m, torch.nn.Linear) and '.layers.0.' in n})\n"
        "l3_lins = sorted({n.split('.')[-1] for n, m in base.named_modules() if isinstance(m, torch.nn.Linear) and '.layers.3.' in n})\n"
        "deltanet_lins = [x for x in l0_lins if x not in ('gate_proj','up_proj','down_proj')]\n"
        "print('LAYER0_LINEARS:', json.dumps(l0_lins))\n"
        "print('LAYER3_LINEARS:', json.dumps(l3_lins))\n"
        "print('DELTANET_LINEARS:', json.dumps(deltanet_lins))\n"
        "targets = sorted(set(['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj', *deltanet_lins]))\n"
        "m = get_peft_model(base, LoraConfig(r=8, lora_alpha=16, target_modules=targets, bias='none', task_type='CAUSAL_LM'))\n"
        f"m.save_pretrained('{canary_dir}', safe_serialization=True)\n"
        "n_ad = sum(1 for k in m.state_dict() if '.lora_A.' in k)\n"
        "print('CANARY_TARGETS:', json.dumps(targets), 'CANARY_MODULES:', n_ad)\n"
    )
    rc_gen, out_gen = sh(f"python3 -c {json.dumps(probe_py)}", timeout=300)
    http_req("http://127.0.0.1:8000/wake_up", "POST")
    if rc_gen == 0:
        st_l, r_l = http_req("http://127.0.0.1:8000/v1/load_lora_adapter", "POST", {
            "lora_name": "deltanet-canary", "lora_path": canary_dir, "load_inplace": True,
        })
        st_c, r_c = (0, None)
        if st_l == 200:
            st_c, r_c = http_req("http://127.0.0.1:8000/v1/chat/completions", "POST", {
                "model": "deltanet-canary", "messages": [{"role": "user", "content": "OK"}],
                "max_tokens": 2, "temperature": 0.0, "chat_template_kwargs": {"enable_thinking": False},
            })
            http_req("http://127.0.0.1:8000/v1/unload_lora_adapter", "POST", {"lora_name": "deltanet-canary"})
        REPORT["deltanet_lora_canary"] = {
            "supported": (st_l == 200 and st_c == 200),
            "load_status": st_l, "infer_status": st_c,
            "load_resp": str(r_l)[:300], "gen_out": out_gen[-500:],
        }
    else:
        REPORT["deltanet_lora_canary"] = {"supported": False, "gen_error": out_gen[-500:]}
finally:
    shutil.rmtree(canary_dir, ignore_errors=True)

REPORT["total_s"] = round(time.time() - T0, 1)
os.makedirs("/content/probe", exist_ok=True)
with open("/content/probe/report.json", "w") as f:
    json.dump(REPORT, f, indent=2)
print("\n===PROBE_REPORT===\n" + json.dumps(REPORT, indent=2), flush=True)
