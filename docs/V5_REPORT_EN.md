# OpenCode & Pi Harness Adapter (V5): Full Technical Report

**Single-GPU Colocated Agentic RL, Multi-Harness Zero-Shot Transfer, Mechanistic GSPO Prefix-Shattering, and 248-Module Weight-vs-Activation Merging Science on Qwen3.5-9B**

- **Codebase**: [XDE10/opencode-harness-adapter](https://github.com/XDE10/opencode-harness-adapter) (`feat/v5-algo-infra-upgrade`)
- **HuggingFace Weights & Artifacts**: [`XDE10/Qwen3.5-9B-Harness-Adapters-v5`](https://huggingface.co/XDE10/Qwen3.5-9B-Harness-Adapters-v5) (8 curated LoRA adapters, 4 Retina explainers, full JSON evaluation & audit suites)
- **Chinese Visual Explainer**: [docs/V5_EXPLAINER_ZH.md](V5_EXPLAINER_ZH.md)

---

## Abstract

Adapting compact open-weight models (`Qwen/Qwen3.5-9B`, non-thinking mode) to operate unmodified terminal coding harnesses via Reinforcement Learning typically requires multi-GPU asynchronous clusters (e.g., 2×B200 + Docker/Harbor). In this report, we present **V5**, a self-contained **single-GPU colocated Agentic RL** system (`1×96 GB` RTX PRO 6000 Blackwell or `1×80 GB` A100, zero Docker) that adapts all **248 linear modules** (Gated DeltaNet + GQA + MLP, LoRA `r=32`) with `0.48s` vLLM sleep offloading, `0.11s` runtime LoRA hot-swapping, `12×–13.5×` prefix-merged multi-turn packing, and exact chunked 248K-vocab LM-head backward (`~39–42 GiB` peak VRAM).

Across **11,220 paired evaluation trials (0 errored trials, 0.0% `<think>` leakage, 0 reward-hacking successes)** spanning **5 benchmark suites** and **3 terminal coding harnesses** (`Pi CLI 0.73.1`, `OpenCode 2.2.7`, and the completely unseen 3rd OOD harness `mini-swe-agent v2`), our adapters achieve:
1. **`+20.00 pp` on official `SWE-bench_Verified` (Pi)**: `23.33% → 43.33%` (`p=0.0002`, `pass@2=53.33%`, `28` wins vs `4` losses) via lossless cross-harness `super_v5_concat_2r`, and **`+11.67 pp` on `SWE-bench_Verified` (OpenCode)**: `34.17% → 45.83%` (`p=0.0057`, `18` wins vs `4` losses) via `v5_oc_main`.
2. **`+10.0 to +12.3 pp` zero-shot OOD harness transfer** on unseen `mini-swe-agent` (`32.31% → 42.31%–44.62%`, `p ≤ 0.0055`), lifting multi-file `repo_pytest` accuracy **8.1×** (`1.7% → 13.8%` with `super_v5_qr_svd`).
3. **Mechanistic RL Algorithm Discovery**: In a controlled 4-way ablation, sequence-level **`GSPO`** ranks last (`43.85%`, n.s.) and slows backward passes **5–6× (`180s → 1,177s`)** because sequence-level `1/N_i` normalization induces redundant `</function></function>` closing tags that Qwen's chat template canonicalizes on the next turn — shattering multi-turn BPE prefix monotonicity (`215` rewrite splits, `29 → 238` segments).
4. **248-Module Merging Science (Weight $\Delta W$ vs Activation $\Delta h$)**: Exact activation covariance over 5,956 heldout coding tokens proves that near-zero weight cosine (`+0.0001`) is a **LoRA-A initialization-seed artifact**, not cross-harness orthogonality. Same-seed cross-harness updates (`OC` vs `Pi s1`) exhibit `ΔW cos = +0.0180` and strong functional alignment `Δh cos = +0.0308`, concentrated **3.4× more strongly in Gated DeltaNet (`+0.0456`) than MLP (`+0.0134`)**. Furthermore, Same-Harness Soup (`soup_v5_pi_qr_svd`) achieves the **highest balanced 5-suite mean (`44.27%`)**, rescuing single-seed OOD collapse (`32.50% → 40.00%` on `SWE-OC`).
5. **Behavioral & Geometric Attribution**: Trajectory audits reveal that RL nearly doubles **Error Recovery Rate** (`25.8% → 47.6%` on `SWE-Pi`, `45.2% → 60.4%` on `SWE-OC`) and raises structured `edit` tool share **3.5×** (`1.5% → 5.3%`), while Frobenius weight-norm analysis (`0.253` for `RFT+RL` vs `0.132` for pure RL) explains why RFT warm-start excels in-distribution (`48.46%` with 30% fewer RL steps) whereas on-policy RL generalizes better on OOD repositories.

---

## 1. Datasets, Isolation Protocol, and Harness Suite

### 1.1 54-Task Multi-File RL Training Pool (`protocol/screen_v5_multifile.json`)
To maximize per-step GRPO variance (avoiding all-pass or all-fail zero-advantage groups), we screened multi-file repositories with `Base Qwen3.5-9B` and froze a **54-task informative pool** (`72.2%` multi-file):
- **27 `SWE-smith-py`** real open-source Python repository bugfix tasks with upstream `pytest` suites;
- **12 L2 `repo_pytest`** 3–4 file synthetic engineering repositories verified by automated triple-control pytest harnesses;
- **15 L1 `single_file`** edge-case algorithmic/state-machine tasks.

During training, dynamic oversampling (`1.5×`), `filter_same_correctness=True`, and `early_cutoff=True` guarantee 6 non-degenerate groups per update step while cancelling straggler rollouts.

### 1.2 Strictly Domain-Isolated Evaluation Suites (11,220 Paired Trials)

| Suite | Benchmark Composition | Harness | Seeds | Trials/Arm | Arms | Total Trials (Errors) |
| :--- | :--- | :--- | :-: | :-: | :-: | :-: |
| `pi_heldout` | 65 domain-disjoint heldout tasks (L1 single-file + L2 `repo_pytest` + L3 real OSS commits) | Pi CLI `0.73.1` | 4 (`101–104`) | 260 | 15 | `3,900` (`0`) |
| `oc_heldout` | Same 65 strictly heldout tasks | OpenCode `2.2.7` | 4 (`101–104`) | 260 | 12 | `3,120` (`0`) |
| `mini_swe_heldout` | Same 65 heldout tasks on **completely unseen 3rd harness** | `mini-swe-agent v2` | 2 (`101–102`) | 130 | 12 | `1,560` (`0`) |
| `swe_verified_pi` | Official 60-task `SWE-bench_Verified` subset (Django, SymPy, etc.) | Pi CLI `0.73.1` | 2 (`101–102`) | 120 | 12 | `1,440` (`0`) |
| `swe_verified_oc` | Same official 60-task `SWE-bench_Verified` subset | OpenCode `2.2.7` | 2 (`101–102`) | 120 | 10 | `1,200` (`0`) |
| **Total** | — | **3 Unmodified CLIs** | — | — | — | **`11,220` (`0`)** |

*Engineering note on `mini-swe-agent v2`*: We patched [oca/harnesses/mini_swe.py](../oca/harnesses/mini_swe.py) (commit `5056d43`) to suppress v2's interactive first-run wizard (`MSWEA_CONFIGURED=true`) and layer overrides cleanly on top of built-in `mini.yaml`, verified via 26 unit tests and a live 1-trial smoke check (`capture_ok=true`, `10` policy turns, `7/7` tests passed in `31.8s`).

---

## 2. Single-GPU Colocated RL Architecture & Protocol

![Training Pipeline](figures/explainer_1_training_pipeline.png)

### 2.1 Five Key Systems Engineering Primitives
1. **Sub-Second Colocation (`vLLM Sleep` + Runtime LoRA Hot-Swap)**: During rollout, vLLM serves BF16 `Qwen3.5-9B` (`~91 GiB` VRAM, concurrency `48`, prefix-cache hit rate `~88%`). Before backward, `/sleep?level=1` offloads KV/weights in **`0.48s`** (`91.0 → 21.6 GiB`); after updating LoRA weights in PyTorch, `/wake_up` + `/v1/load_lora_adapter` hot-swaps the new adapter in **`0.10–0.12s`** (`0` vLLM restarts across 400+ steps).
2. **Engine-Boundary `CaptureProxy` (`oca/proxy.py`)**: Sits transparently between unmodified CLIs and vLLM, capturing exact `return_token_ids` and `processed_logprobs` from the serving engine, isolating non-policy auxiliary calls (e.g., OpenCode title summarizers), and enforcing `safe_intercept=True`.
3. **Prefix-Merged Multi-Turn Packing (`oca/train.py`)**: Merges monotonic multi-turn histories into packed super-sequences (**`12.2×–13.0×`** compression on Pi: `~400` turns → `~31` segments; gradient cosine `0.989`), automatically splitting segments when a harness rewrites or compacts prior context.
4. **Exact Chunked LM-Head Backward**: Computes exact cross-entropy/logprob gradients in `2048`-token chunks across Qwen3.5's 248K vocabulary (`max_lp_diff = 0.000e+00`), capping peak training VRAM at **`40.5–42.1 GiB`** (vs `>100 GiB` OOM unchunked).
5. **Full 248-Module Hybrid-Architecture LoRA**: Adapts all GQA (`q/k/v/o_proj`), MLP (`gate/up/down_proj`), and **Gated DeltaNet** (`in_proj_qkv/z/b/a`, `out_proj`) projections (`r=32, alpha=64`, `346 MB` per checkpoint).

### 2.2 Frozen Hyperparameters (`protocol/oca-v5.json`)

| Category | Parameters |
| :--- | :--- |
| **Model & LoRA** | `Qwen/Qwen3.5-9B` (BF16, `enable_thinking=False`, `qwen3_coder`), 248-module LoRA `r=32, alpha=64` (`max_lora_rank=64`), default init seed `2026` (`v5_pi_seed2`: `2027`) |
| **Rollout & Sandbox** | `temp=0.8`, `top_p=1.0`, `max_ctx=32768`, `max_out/call=2048`, `max_out/trial=10240`, `max_calls=24`, `timeout=300s`, `/dev/shm` workdir, unprivileged `agent` UID + `bwrap`, hidden `0700` tests graded as `nobody` |
| **Reward & Anti-Hack** | Binary hidden test pass + efficiency bonus (`eff_w=0.05`, budget `24` turns / `8192` tok) + static/bash/test-tamper zeroing (`10/10` adversarial exploits blocked) |
| **RL Optimization** | `50` steps (`35` for `v5_rft_plus_rl`), `6 tasks × 4 rollouts` (`1.5×` oversample), `minibatches=2`, `lr=2e-5`, `max_grad_norm=1.0`, `Dr.GRPO` + `TIS-Clip` (`tis_cap=2.0`, `clip_low=0.20`, `clip_high=0.28`), token-level normalization |

---

## 3. RL Algorithm Ablation, 7-Run Telemetry & GSPO Mechanism

![GSPO Discovery](figures/explainer_3_gspo_discovery.png)

### 3.1 Full 7-Run Training Telemetry (`artifacts/v5_final/training_curves_full.json`)

| Training Run | Steps | First-10 Pass | Last-10 Pass | Peak Pass | Packed Segs *(med/max)* | Med Comp | Max Rewrite Splits | Train Time *(med/max)* | LoRA Swap | Mean Logp Err | Peak VRAM | Wall Time |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `v5_pi_drgrpo_tis` | 50 | `68.9%` | **`71.4%`** | **`90.9%`** | `31 / 42` | `12.21×` | `18` | `157s / 406s` | `0.104s` | `0.00505` | `40.7 GiB` | `8.11 h` |
| `v5_pi_cispo` | 50 | `62.1%` | `60.9%` | `81.2%` | `31 / 40` | **`12.97×`** | `17` | `205s / 652s` | `0.365s` | `0.00496` | `40.6 GiB` | `10.57 h` |
| `v5_pi_gspo` ⚠️ | 50 | `67.5%` | `60.4%` | `82.5%` | **`67 / 238`** | **`5.58×`** *(1.71×)* | **`215`** | **`319s / 1177s`** | `0.103s` | `0.00498` | `42.1 GiB` | `11.44 h` |
| `v5_pi_turn_credit` | 50 | `70.1%` | `69.9%` | `85.4%` | `32 / 47` | `10.84×` | `23` | `157s / 219s` | `0.120s` | `0.00486` | `40.9 GiB` | `8.10 h` |
| `v5_oc_main` | 50 | `56.8%` | `67.1%` | `87.5%` | `66 / 135` | `5.72×` | `111` | `377s / 816s` | `0.112s` | `0.00507` | `40.5 GiB` | `11.65 h` |
| `v5_joint_oc_pi` | 50 | `50.3%` | `56.1%` | `72.7%` | `42 / 62` | `8.79×` | `38` | `281s / 446s` | `0.441s` | `0.00534` | `40.5 GiB` | `12.90 h` |
| `v5_rft_plus_rl` | 35 | `69.3%` | `70.9%` | `80.8%` | `32 / 45` | `11.76×` | `21` | `171s / 255s` | `0.106s` | `0.00440` | `40.6 GiB` | **`5.75 h`** |

*(An 8th run, `v5_pi_seed2`, trained 50 steps on an 80 GB A100 with `lora_init_seed=2027` and rollout `seed=102`, peaking at `79.2%` with `24–40` packed segments.)*

### 3.2 Mechanistic Failure Analysis of Sequence-Level `GSPO`
On the controlled Pi 4-way ablation (`pi_heldout`, 260 trials/arm):
- **`Dr.GRPO + TIS`**: **`47.31%`** (`+10.38 pp`, `p=0.0049`, `pass@4=69.23%`, `+17.3%` common-solved token savings)
- **`CISPO`**: `46.15%` (`+9.23 pp`, `p=0.0247`, **shortest mean tokens `4,022`**, **`+31.66%` common-solved token savings**)
- **`Turn-Credit`**: `45.77%` (`+8.85 pp`, `p=0.0164`, **fewest mean turns `13.57`**)
- **`GSPO`**: **`43.85%`** (`+6.92 pp`, `p=0.0677` n.s., worst of all 4 RL runs)

**Root Cause**: Because GSPO normalizes log-ratios across the entire sequence ($1/N_i$), redundant end-of-turn closing tokens (`</function>\n</function>\n</tool_call>`) receive diluted per-token penalties. Tolerant tool parsers execute the tool call without error, but on the subsequent turn Qwen's chat template re-renders the historical tool call into canonical single-tag form (`</function>\n</tool_call>`). This silent historical rewrite violates multi-turn BPE prefix monotonicity, forcing `215` prefix-rewrite splits at step 50 (`29 → 238` packed segments, `1.71×` compression, `1,177s` backward pass) and yielding the highest safe-intercept count (`9`) during blind evaluation.

---

## 4. Complete 11,220-Trial Evaluation Results

![Benchmark Results](figures/explainer_2_benchmark_results.png)

### 4.1 5-Benchmark Master Table (`Pass@1`, Task-Level Permutation `p`, 0 Errored Trials)

| Adapter / Method | **5-Suite Mean** | 3-Heldout Mean | 2-SWE Mean | Pi Heldout *(65×4)* | OC Heldout *(65×4)* | OOD `mini-swe` *(65×2)* | SWE-Verified Pi *(60×2)* | SWE-Verified OC *(60×2)* |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `Base Qwen3.5-9B` | `33.12%` | `36.03%` | `28.75%` | `36.92%` | `38.85%` | `32.31%` | `23.33%` | `34.17%` |
| `v5_pi_seed2` | **`45.22%`** | **`50.64%`** | `37.09%` | **`56.15%`** *(p=.0001)* | **`51.15%`** *(p=.0018)* | **`44.62%`** *(p=.0018)* | `41.67%` *(p=.0003)* | `32.50%` *(p=.865)* |
| **`soup_v5_pi_qr_svd`** | **`44.27%`** | `46.28%` | `41.25%` | `47.69%` *(p=.0022)* | `48.85%` *(p=.0135)* | `42.31%` *(p=.0387)* | `42.50%` *(p=.0007)* | `40.00%` *(p=.347)* |
| `v5_pi_drgrpo_tis` | `43.55%` | `45.64%` | `40.41%` | `47.31%` *(p=.0049)* | `47.31%` *(p=.0121)* | `42.31%` *(p=.0049)* | `40.83%` *(p=.0003)* | `40.00%` *(p=.209)* |
| `soup_v5_pi_concat_2r` | `43.05%` | `47.31%` | `36.66%` | `54.62%` *(p=.0001)* | `45.77%` *(p=.0945)* | `41.54%` *(p=.0117)* | `40.00%` *(p=.0009)* | `33.33%` *(p=1.00)* |
| `v5_joint_oc_pi` | `42.67%` | `43.33%` | **`41.66%`** | `46.92%` *(p=.0087)* | `43.85%` *(p=.1645)* | `39.23%` *(p=.0479)* | `38.33%` *(p=.0057)* | `45.00%` *(p=.0298)* |
| `super_v5_qr_svd` | `42.45%` | `46.03%` | `37.08%` | `47.31%` *(p=.0050)* | `47.69%` *(p=.0054)* | `43.08%` *(p=.0055)* | `35.83%` *(p=.0353)* | `38.33%` *(p=.494)* |
| `super_v5_concat_2r` | `42.33%` | `43.33%` | `40.83%` | `45.00%` *(p=.0499)* | `47.31%` *(p=.0062)* | `37.69%` *(p=.0654)* | **`43.33%`** *(p=.0002)* | `38.33%` *(p=.471)* |
| `v5_oc_main` | `42.06%` | `43.72%` | `39.58%` | `45.00%` *(p=.0232)* | `46.15%` *(p=.0621)* | `40.00%` *(p=.0529)* | `33.33%` *(p=.0781)* | **`45.83%`** *(p=.0057)* |
| `super_v5_ties` | `40.76%` | `41.54%` | `39.59%` | `41.54%` *(p=.0584)* | `45.38%` *(p=.0196)* | `37.69%` *(p=.2349)* | `37.50%` *(p=.0042)* | `41.67%` *(p=.144)* |
| `v5_rft_plus_rl` *(35 RL)* | — | `44.61%` | — | `48.46%` *(p=.0015)* | `46.92%` *(p=.0151)* | `38.46%` *(p=.076)* | `34.17%` *(p=.0212)* | — |
| `v5_rft_only` | — | `37.18%` | — | `38.08%` *(p=.777)* | `39.62%` *(p=.903)* | `33.85%` *(p=.835)* | `26.67%` *(p=.557)* | — |

### 4.2 Granular Tier Breakdowns (`repo_pytest` vs `single_file`), `pass@k`, and Paired Wins/Losses
- **Multi-file `repo_pytest` gains dominate across every harness**:
  - `pi_heldout`: `12.1% (Base) → 24.1%` (`v5_pi_drgrpo_tis`, `2.0×`) → **`32.8%`** (`soup_v5_pi_concat_2r`, `2.7×`); `pass@4` climbs from `55.38% → 69.23%–72.31%`.
  - `oc_heldout`: `12.1% (Base) → 21.6%` (`soup_v5_pi_qr_svd`) → **`26.7%`** (`v5_pi_seed2`, `2.2×`); `pass@4` climbs from `55.38% → 66.15%–67.69%`.
  - Unseen `mini_swe_heldout`: `1.7% (Base) → 10.3%` (`v5_pi_drgrpo_tis`, `6.0×`) → **`13.8%`** (`super_v5_qr_svd`, **`8.1×`**); `pass@2` climbs from `36.92% → 55.38%` (`+18.46 pp`).
- **Official `SWE-bench_Verified` paired outcomes**:
  - `swe_verified_pi`: `super_v5_concat_2r` achieves **`28 wins / 4 losses`** (`7:1`), `pass@2 = 53.33%` (vs `31.67%` Base), cutting common-solved tokens by **`-13.55%`**.
  - `swe_verified_oc`: `v5_oc_main` achieves **`18 wins / 4 losses`** (`4.5:1`, `pass@2 = 55.00%`), while `v5_joint_oc_pi` reaches **`pass@2 = 56.67%`** (`20 wins / 7 losses`).

---

## 5. Trajectory & Behavioral Audit (11,220 Trials)

Auditing every trajectory via `oca/audit_trajectories.py` establishes three clean behavioral findings:
1. **Cleanliness & Integrity**: `0.0%` `<think>` tag leakage across all 11,220 trials; `0` reward-hacking successes.
2. **Error Recovery Rate Nearly Doubles**:
   - `SWE-Verified (Pi)`: `25.8% (Base) → 45.1% (v5_pi_drgrpo_tis) → 47.6% (super_v5_concat_2r)` (`+21.8 pp`)
   - `SWE-Verified (OC)`: `45.2% (Base) → 55.6% (v5_oc_main) → 60.4% (v5_joint_oc_pi)` (`+15.2 pp`)
   - `Pi Heldout`: `27.2% (Base) → 37.8% (super_v5_qr_svd) → 46.3% (v5_pi_seed2)` (`+19.1 pp`)
   - `OOD mini-swe`: `23.2% (Base) → 33.3% (v5_pi_drgrpo_tis) → 37.0% (v5_pi_seed2)` (`+13.8 pp`)
3. **Tool-Use & Failure-Taxonomy Shift on `SWE-Verified (Pi)`**:
   - `Base` spends `77.7%` of tool calls looping in `bash` and only **`1.5%`** on structured `edit`, suffering `81/120` `budget_or_timeout` failures (`28` solved).
   - `v5_pi_drgrpo_tis` reduces `bash` to `69.0%`, raises `read` to `25.5%`, and increases structured **`edit` share 3.5× (`1.5% → 5.3%`)**; `super_v5_concat_2r` cuts `budget_or_timeout` failures by **`-28.4%`** (`81 → 58`) while nearly doubling solved trials (`28 → 52`).

---

## 6. 248-Module Merging Science: Weight ($\Delta W$), Activation ($\Delta h$), and Weight Geometry

![Merging Science](figures/explainer_4_merging_science.png)

### 6.1 Exact Activation Covariance vs Weight Cosine
We collected input activation covariance matrices $C_m = \frac{1}{N} X_m^\top X_m$ across all **248 LoRA modules** over 16 heldout coding prompts (`5,956` tokens/module) on base `Qwen3.5-9B`, computing exact $\cos(\Delta W_1, \Delta W_2)$ and $\cos(\Delta W_1 X, \Delta W_2 X)$ via $\mathrm{Tr}((B_1^\top B_2)(A_2 C_m A_1^\top))$:

| Adapter Pair | Init Seed Match | $\Delta W$ All | DeltaNet $\Delta W$ | GQA $\Delta W$ | MLP $\Delta W$ | **$\Delta h$ All** | **DeltaNet $\Delta h$** | **GQA $\Delta h$** | **MLP $\Delta h$** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `OC` vs `Pi s1` (Cross-Harness) | Same (`2026`) | `+0.0180` | `+0.0245` | `+0.0188` | `+0.0095` | **`+0.0308`** | **`+0.0456`** | `+0.0279` | `+0.0134` |
| `Dr.GRPO` vs `CISPO` (Same-Harness) | Same (`2026`) | `+0.0181` | `+0.0172` | `+0.0218` | `+0.0179` | `+0.0183` | `+0.0135` | `+0.0308` | `+0.0201` |
| `Dr.GRPO` vs `Turn-Credit` | Same (`2026`) | `+0.0184` | `+0.0226` | `+0.0079` | `+0.0168` | `+0.0163` | `+0.0190` | `+0.0071` | `+0.0161` |
| `Joint` vs `Pi s1` | Same (`2026`) | `+0.0173` | `+0.0164` | `+0.0168` | `+0.0186` | `+0.0212` | `+0.0204` | `+0.0234` | `+0.0215` |
| `OC` vs `Pi s2` (Cross-Harness) | Diff (`26/27`) | `+0.0001` | `+0.0001` | `+0.0001` | `+0.0001` | **`+0.0165`** | `+0.0178` | `+0.0201` | `+0.0138` |
| `Pi s1` vs `Pi s2` (Same-Harness) | Diff (`26/27`) | **`+0.0001`** | `+0.0002` | `+0.0001` | `+0.0001` | `+0.0079` | `+0.0023` | `+0.0172` | `+0.0119` |

### 6.2 Adapter Weight Geometry (Frobenius Norms & Effective Rank)

| Adapter | Mean Frob (DeltaNet) | Mean Frob (GQA) | Mean Frob (MLP) | Mean Effective Rank (of 32) |
| :--- | :---: | :---: | :---: | :---: |
| Pure RL runs (`v5_oc_main`, `v5_pi_*`, `v5_joint_oc_pi`) | `0.060–0.065` | `0.073–0.078` | `0.126–0.135` | `16.13–16.45` |
| `v5_rft_only` (2-epoch SFT on 175 trajectories) | **`0.108`** | **`0.132`** | **`0.227`** *(1.8× RL)* | `17.64` |
| `v5_rft_plus_rl` (RFT + 35-step RL) | **`0.121`** | **`0.147`** | **`0.253`** *(2.0× RL)* | `17.23` |

**Key Takeaways**:
- **Orthogonality is seed-driven, functional alignment is DeltaNet-driven**: Changing LoRA-A init seed collapses even same-harness $\Delta W$ cosine to `+0.0001`, whereas same-seed cross-harness updates align strongly in activation space (`+0.0456` in Gated DeltaNet — `3.4×` higher than MLP).
- **Rank-truncation vs denoising trade-off**: Merging orthogonal diff-seed adapters (`Pi s1 + Pi s2`) with rank-32 `QR-SVD` sacrifices `-6.93 pp` vs lossless rank-64 `Concat-2r` on `pi_heldout` (`47.69%` vs `54.62%`), yet `QR-SVD`'s low-rank compression denoises `seed2`'s OOD failure on `SWE-OC` (`32.50% → 40.00%`) to deliver the best balanced 5-suite mean (`44.27%`).
- **Geometric explanation for RFT vs RL**: SFT moves `1.8×–2.0×` farther from Base in Frobenius norm than 50-step on-policy RL, accounting for `v5_rft_plus_rl`'s superior in-distribution efficiency (`48.46%` on `pi_heldout` with 30% fewer RL steps) alongside weaker OOD repo transfer (`34.17%` vs `40.83%` on `SWE-Verified Pi`).

---

## 7. Threats to Validity, Limitations & Future Work

1. **High Single-Seed Variance in Multi-Turn Agentic RL**: `v5_pi_seed2` reaches `56.15%` on `pi_heldout` yet drops below Base (`32.50%`) on `swe_verified_oc`. Multi-seed evaluation and multi-adapter soup/merging are essential rather than optional.
2. **Protocol Dilution Under Equal-Weight 0.5/0.5 Merging**: On `swe_verified_oc`, matched `v5_oc_main` (`45.83%`) and `v5_joint_oc_pi` (`45.00%`) outperform equal-weight merges (`38.33%`). Layer-selective merging (e.g., merging Gated DeltaNet while keeping harness-specific MLP projections) or asymmetric weights (`0.7 / 0.3`) is a promising next step.
3. **Subprocess Memory Capping**: Runaway agent-generated Python test scripts can leak host RAM during parallel evaluation; adding strict per-trial `RLIMIT_AS` enforcement in `oca/rollout.py` will harden unattended runs.
4. **Non-Thinking Focus**: All V5 runs target low-latency `enable_thinking=False`; extending colocated RL to adaptive thinking-budget control remains future work.
