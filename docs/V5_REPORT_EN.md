# OpenCode & Pi Harness Adapter (V5): Technical Report

**Single-GPU Colocated Agentic RL, Multi-Harness Transfer, GSPO Prefix-Shattering Mechanism, and Weight-vs-Activation Merging Science on Qwen3.5-9B**

- **Base Model**: `Qwen/Qwen3.5-9B` (`enable_thinking=False`, hybrid Gated DeltaNet + GQA + MLP architecture)
- **Adapters**: Full-coverage **248-module LoRA (`r=32, alpha=64`)** across `linear_attn`, `self_attn`, and `mlp` projections
- **Training Pool**: 54 strictly domain-isolated multi-file coding tasks (`27 SWE-smith-py` + `12 L2 repo_pytest` + `15 L1`), screened for `1..3/4` pass-rate informativeness
- **Evaluation Scale**: **11,220 paired rollout trials** across **5 benchmark suites** and **3 coding harnesses** (`Pi CLI 0.73.1`, `OpenCode 2.2.7`, and unseen 3rd OOD harness `mini-swe-agent v2`), with **0 errored trials**, **0.0% `<think>` tag leakage**, and **0 reward-hacking successes**.
- **HuggingFace Release**: [`XDE10/Qwen3.5-9B-Harness-Adapters-v5`](https://huggingface.co/XDE10/Qwen3.5-9B-Harness-Adapters-v5)

---

## 1. Executive Summary & Core Findings

1. **Strong Real-Repo & Unseen-Harness Transfer (`+20.0 pp` on SWE-bench Verified, `+12.3 pp` on Unseen 3rd Harness)**
   - On official 60-task `SWE-bench_Verified` (2 seeds = 120 trials/arm), `super_v5_concat_2r` lifts `Pi` accuracy from **`23.33% → 43.33%` (`+20.00 pp`, permutation `p=0.0002`)**, while matched `v5_oc_main` lifts `OpenCode` from **`34.17% → 45.83%` (`+11.67 pp`, `p=0.0057`)**.
   - On the completely unseen 3rd harness `mini-swe-agent` (65 heldout × 2 seeds = 130 trials/arm), RL adapters trained solely on Pi/OpenCode transfer zero-shot from **`32.31% → 42.31%–44.62%` (`+10.0 to +12.3 pp`, `p ≤ 0.0055`)**.

2. **Mechanistic RL Algorithm Discovery: Sequence-Level `GSPO` Breaks Multi-Turn BPE Prefix Monotonicity**
   - Controlled 50-step Pi ablation on the identical 54-task pool ranks: **`Dr.GRPO + TIS-Clip` (`47.31%`, `p=0.0049`) > `CISPO` (`46.15%`, `p=0.0247`, shortest tokens `4,022`) > `Turn-Credit` (`45.77%`, `p=0.0164`, fewest turns `13.57`) > `GSPO` (`43.85%`, `p=0.0677`, n.s.)**.
   - Step-by-step telemetry pinpoints the root cause: sequence-level `1/N_i` normalization in `GSPO` induces redundant closing tags (`</function>\n</function>\n</tool_call>`). Tolerant tool parsers accept them, but Qwen's chat template canonicalizes historical messages back to a single `</function>` on the next turn — shattering multi-turn BPE prefix monotonicity (`215` prefix-rewrite splits at step 50), inflating packed segments from **`29 → 238`** (`1.71×` compression vs `12×`), and slowing backward passes by **5–6× (`180s → 1,177s`)**, while also triggering the highest safe-intercept count (`9`) during blind evaluation.

3. **Debunking the "Cross-Harness Orthogonal Subspace" Myth via 248-Module Activation Covariance**
   - Using exact Frobenius inner products ($\Delta W$) and real heldout coding activation covariance ($\mathrm{Tr}(B_1^\top B_2 A_2 C A_1^\top)$ over 5,956 tokens across all 248 modules), we prove that near-zero weight cosine (`+0.0001`) is **an artifact of distinct LoRA-A initialization seeds**, NOT a cross-harness property:
     - Same-harness different-seed (`Pi s1` vs `Pi s2`, seeds `2026`/`2027`): `ΔW cos = +0.0001`, `Δh cos = +0.0079`.
     - Cross-harness same-seed (`OC` vs `Pi s1`, seed `2026`): `ΔW cos = +0.0180` (identical to same-harness cross-algorithm `Dr.GRPO vs CISPO = +0.0181`), and **higher functional activation alignment `Δh cos = +0.0308`**, concentrated strongly in **Gated DeltaNet layers (`+0.0456`) > GQA (`+0.0279`) > MLP (`+0.0134`)**.
   - **Empirical Merging Law**:
     - When merging truly orthogonal different-seed adapters (`Pi s1 + Pi s2`, `ΔW cos = +0.0001`), rank-32 truncation (`soup_v5_pi_qr_svd`) discards subspace energy on `pi_heldout` (`47.69%` vs lossless rank-64 `soup_v5_pi_concat_2r` `54.62%`, `-6.93 pp`), yet acts as a strong denoiser that rescues `v5_pi_seed2`'s `SWE-OC` collapse (`32.50% → 40.00%`) to achieve the **highest balanced 5-suite macro-average (`44.27%`, zero suite below 40%)**.
     - Cross-harness merging beats Joint-RL on all 3 heldout suites (`46.03%` vs `43.33%` mean) and sets the all-time #1 on `SWE-Verified (Pi)` (`super_v5_concat_2r`: **`43.33%`**), whereas matched-harness `v5_oc_main` (`45.83%`) and `v5_joint_oc_pi` (`45.00%`) win on `SWE-Verified (OC)` where 0.5/0.5 averaging dilutes OpenCode's repo-navigation protocol.

4. **RFT Warm-Start vs From-Scratch RL Trade-Off**
   - Pure rejection-sampling SFT (`v5_rft_only`, 175 passing base trajectories) yields negligible blind gain (`+0.77 to +1.54 pp`, `p > 0.55`).
   - Adding just **35 RL steps** (`v5_rft_plus_rl`, 30% less RL compute) reaches **`48.46%` (`+11.54 pp`, `p=0.0015`)** on `pi_heldout` (beating 50-step `v5_pi_drgrpo_tis` `47.31%`) and transfers `+8.08 pp` to `oc_heldout`, though 50-step from-scratch RL generalizes better on OOD GitHub repos (`SWE-Verified Pi`: `40.83%` vs `34.17%`).

5. **Trajectory Audit: Error-Recovery Rate Nearly Doubles**
   - Across all 11,220 evaluated trials, the primary behavioral mechanism explaining RL gains is a dramatic jump in **Error Recovery Rate** (fraction of trials encountering a bash/test error that recover and pass):
     - `SWE-Verified (Pi)`: `25.8% (Base) → 47.6% (super_v5_concat_2r)`
     - `SWE-Verified (OC)`: `45.2% (Base) → 60.4% (v5_joint_oc_pi)`
     - `Pi Heldout`: `27.2% (Base) → 46.3% (v5_pi_seed2)`
     - `OOD mini-swe`: `23.2% (Base) → 37.0% (v5_pi_seed2)`

---

## 2. Complete 5-Benchmark Evaluation Matrix (11,220 Paired Trials)

All comparisons report paired `pass@1`, delta in percentage points (`Δ`), and two-sided **task-level permutation test `p`** (zero errored trials in every cell):

| Adapter / Method | **5-Suite Mean** | Pi Heldout *(65×4)* | OC Heldout *(65×4)* | OOD `mini-swe` *(65×2)* | SWE-Verified Pi *(60×2)* | SWE-Verified OC *(60×2)* |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `Base Qwen3.5-9B` | `33.12%` | `36.92%` | `38.85%` | `32.31%` | `23.33%` | `34.17%` |
| `v5_pi_seed2` | **`45.22%`** | **`56.15%`** *(p=0.0001)* | **`51.15%`** *(p=0.0018)* | **`44.62%`** *(p=0.0018)* | `41.67%` *(p=0.0003)* | `32.50%` *(p=0.865)* |
| `soup_v5_pi_qr_svd` | **`44.27%`** | `47.69%` *(p=0.0022)* | `48.85%` *(p=0.0135)* | `42.31%` *(p=0.0387)* | `42.50%` *(p=0.0007)* | `40.00%` *(p=0.347)* |
| `v5_pi_drgrpo_tis` | `43.55%` | `47.31%` *(p=0.0049)* | `47.31%` *(p=0.0121)* | `42.31%` *(p=0.0049)* | `40.83%` *(p=0.0003)* | `40.00%` *(p=0.209)* |
| `soup_v5_pi_concat_2r` | `43.05%` | `54.62%` *(p=0.0001)* | `45.77%` *(p=0.0945)* | `41.54%` *(p=0.0117)* | `40.00%` *(p=0.0009)* | `33.33%` *(p=1.000)* |
| `v5_joint_oc_pi` | `42.67%` | `46.92%` *(p=0.0087)* | `43.85%` *(p=0.1645)* | `39.23%` *(p=0.0479)* | `38.33%` *(p=0.0057)* | `45.00%` *(p=0.0298)* |
| `super_v5_qr_svd` | `42.45%` | `47.31%` *(p=0.0050)* | `47.69%` *(p=0.0054)* | `43.08%` *(p=0.0055)* | `35.83%` *(p=0.0353)* | `38.33%` *(p=0.494)* |
| `super_v5_concat_2r` | `42.33%` | `45.00%` *(p=0.0499)* | `47.31%` *(p=0.0062)* | `37.69%` *(p=0.0654)* | **`43.33%`** *(p=0.0002)* | `38.33%` *(p=0.471)* |
| `v5_oc_main` | `42.06%` | `45.00%` *(p=0.0232)* | `46.15%` *(p=0.0621)* | `40.00%` *(p=0.0529)* | `33.33%` *(p=0.0781)* | **`45.83%`** *(p=0.0057)* |
| `super_v5_ties` | `40.76%` | `41.54%` *(p=0.0584)* | `45.38%` *(p=0.0196)* | `37.69%` *(p=0.2349)* | `37.50%` *(p=0.0042)* | `41.67%` *(p=0.144)* |
| `v5_rft_plus_rl` *(35 RL)* | — | `48.46%` *(p=0.0015)* | `46.92%` *(p=0.0151)* | `38.46%` *(p=0.076)* | `34.17%` *(p=0.0212)* | — |
| `v5_rft_only` | — | `38.08%` *(p=0.777)* | `39.62%` *(p=0.903)* | `33.85%` *(p=0.835)* | `26.67%` *(p=0.557)* | — |
| `v5_pi_cispo` *(50 RL)* | — | `46.15%` *(p=0.0247)* | — | — | — | — |
| `v5_pi_turn_credit` *(50 RL)* | — | `45.77%` *(p=0.0164)* | — | — | — | — |
| `v5_pi_gspo` *(50 RL)* | — | `43.85%` *(p=0.0677)* | — | — | — | — |

---

## 3. Merging Science: Weight-Space ($\Delta W$) vs Activation-Space ($\Delta h$) Cosine

Computed across all **248 LoRA modules** (`linear_attn` Gated DeltaNet, `self_attn` GQA, and `mlp`) using exact input activation covariance $C_m = \frac{1}{N} X_m^\top X_m$ collected over 16 heldout coding prompts (`5,956` tokens/module):

| Adapter Pair | Init Seed Match | Weight $\Delta W$ All | DeltaNet $\Delta W$ | GQA $\Delta W$ | MLP $\Delta W$ | **Activation $\Delta h$ All** | **DeltaNet $\Delta h$** | **GQA $\Delta h$** | **MLP $\Delta h$** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `OC` vs `Pi s1` (Cross-Harness) | Same (`2026`) | `+0.0180` | `+0.0245` | `+0.0188` | `+0.0095` | **`+0.0308`** | **`+0.0456`** | `+0.0279` | `+0.0134` |
| `Dr.GRPO` vs `CISPO` (Same-Harness) | Same (`2026`) | `+0.0181` | `+0.0172` | `+0.0218` | `+0.0179` | `+0.0183` | `+0.0135` | `+0.0308` | `+0.0201` |
| `Dr.GRPO` vs `Turn-Credit` | Same (`2026`) | `+0.0184` | `+0.0226` | `+0.0079` | `+0.0168` | `+0.0163` | `+0.0190` | `+0.0071` | `+0.0161` |
| `Joint` vs `Pi s1` | Same (`2026`) | `+0.0173` | `+0.0164` | `+0.0168` | `+0.0186` | `+0.0212` | `+0.0204` | `+0.0234` | `+0.0215` |
| `OC` vs `Pi s2` (Cross-Harness) | Diff (`26`/`27`) | `+0.0001` | `+0.0001` | `+0.0001` | `+0.0001` | **`+0.0165`** | `+0.0178` | `+0.0201` | `+0.0138` |
| `Pi s1` vs `Pi s2` (Same-Harness) | Diff (`26`/`27`) | **`+0.0001`** | `+0.0002` | `+0.0001` | `+0.0001` | `+0.0079` | `+0.0023` | `+0.0172` | `+0.0119` |

---

## 4. Systems Engineering Telemetry (Single 96 GB G4 / 80 GB A100)

- **vLLM Colocation**: `sleep(level=1)` in `0.48s` (`91.0 → 21.6 GiB`), `/wake_up` + runtime LoRA hot-swap in `0.56s` (`lora_swap_only = 0.10–0.12s`), zero vLLM restarts across 400+ RL steps.
- **Prefix-Merged Multi-Turn Packing**: `12×–13.5×` segment compression (`~400` raw turns → `26–36` packed segments, `~180s` backward step) on Pi; auto-splits safely on OpenCode context compaction (`60–135` segments).
- **Exact Chunked LM-Head Backward (248K Vocab)**: peak training VRAM `~39.3 GiB` (vs >100 GiB OOM unchunked), `0 NaN` across 400+ steps, mean BF16 vLLM↔PyTorch logprob error `0.0045–0.0053 nats`.
- **Visual Explainers**: See [`docs/V5_EXPLAINER_ZH.md`](V5_EXPLAINER_ZH.md) and `docs/figures/explainer_{1..4}_*.png`.
