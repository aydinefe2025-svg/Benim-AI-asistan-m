# CANO — VO-MASD upstream codebook CPU smoke and launch guard

**Date:** 2026-11-05. **Scientific status:** component-level synthetic smoke only;
**not** reproduction of any IJCAI paper win rate, source training, skill grouping,
SMAC/StarCraft evaluation, or real multi-agent dataset.

## Verified original provenance
- Research paper: *Variational Offline Multi-agent Skill Discovery* (IJCAI 2025), DOI https://doi.org/10.24963/ijcai.2025/538.
- Upstream repo: https://github.com/LucasCJYSDL/VOMASD . MIT copyright (c) 2024 Jiayu Chen; license reproduced in `LICENSE_UPSTREAM_MIT.txt`.
- Code path (Hier): `VO-MASD/onpolicy/algorithms/vomasd/vomasd_hier_policy.py`; GitHub blob `621980122d13f1c8dab31c4ccabe9f5c4099c95f`. `upstream_vomasd_quantizer.py` contains only the **transcribed mathematical method** `forward_codebook` as a standalone class with equivalent PyTorch operators; no runtime dependency on original package or its full model graph.
- Original launcher `VO-MASD/onpolicy/scripts/train_smac_scripts/train_marine.sh` GitHub blob `40e9a621e7dd89fef427504da4959fcd4db7ae8f`: archived verbatim as `train_marine_upstream.sh`, verified by `git hash-object`. This is **read only**; never execute the original 8,000,000-step script during a smoke test.
- Launcher defaults: `algo="odis"`, map `10m`, seed `3`, GPU `CUDA_VISIBLE_DEVICES=3`, training steps `8,000,000`; to test VO-MASD, the algorithm must be explicitly changed and the SC2/SMAC setup installed.

## Reproducible CPU smoke
Dependencies: Python 3.12+ and CPU PyTorch (tested on torch 2.10.0+cpu; no GPU required). No StarCraft or internet calls at run time.

```bash
cd src
python -W error::ResourceWarning -m unittest -q test_vomasd_cpu
python toy_quantizer.py --output ../evidence/toy_results.json
python preflight.py train_marine_upstream.sh --output ../evidence/upstream_preflight.json
```

The last `preflight` command intentionally exits **3** because the reference script selects **ODIS** rather than VO-MASD. This safety failure is the expected result. No shell command is executed by the preflight.

On 320 seeded training and 120 separately sampled held-out **synthetic 4-dimensional latent vectors**, the isolated codebook's nearest-neighbor quantizer was trained with Adam for 120 steps. Test MSE went from `0.963508` to `0.165233` (**82.851% reduction**); all four codes used. In eight seeds, all held-out losses improved; see `evidence/multi_seed.json`. This measures only codebook quantization of toy representations; it does not prove coordinated behavior, subgroup discovery, agent training, or a claimed paper result.

## Scope and next milestone
1. Full authentic VO-MASD requires the paper's training setup, compatible Torch and SMAC/SC2, datasets/checkpoints, explicit `vomasd-3d` or `vomasd-hier`, seeds and baselines, plus paper-defined win-rate metrics.
2. Set up isolated environment with bounded compute and verify upstream dependencies/licenses and dataset hashes before any expensive training.
3. Benchmark VO-MASD vs ODIS with identical data, seeds and settings; archive raw metrics and uncertainty. **Not attempted in this report.**
