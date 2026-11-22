# F68 — F67 PCHIP-cold direct RNS two-mesh diagnostic

**Run date:** 2026-11-19  
**Status:** `PASS_DIRECT_RNS_TWO_MESH_EXPLORATORY_ONLY`  
**Final fully successful run:** [44490729799](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44490729799)  
**Final Actions artifact:** [14512464947](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44490729799/artifacts/14512464947)  
**Tested PR:** [#635](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/635)  
**Tested branch commit:** `759b3b3b5c389417cdea38daeb73c0b5d7720068`  
**Actions merge ref:** `aa585bffb1d041142fa1404d92839b37dd7a6c1d`  
**RNS upstream revision:** `97e85d325a33e37f702306414533f6cd77812477`

## Scope

This run took the separately named F67 alternative numerical EOS, `MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL`, and solved static and uniformly rotating GR configurations with direct RNS C roots at 346.536369 Hz. Targets were 2.073, 2.175, 2.200 and 2.250 M☉ using 151- and 196-point meshes. It is an exploratory numerical gravity diagnostic; it does not certify a physical EOS or constitute the seven-original-EOS Bayesian analysis.

The original installed LALSuite 7.26.4 MPA1 table was source-pinned and verified in the run: SHA-256 `bd1b0c1a0506f37649275bfe401cf985f78b31e7d5dc3023665c49b9e2d0c3ec`. Six F68 table conversion tests passed. The output precision patch changed formatting only; the recorded log states `physics_equations_changed: false`.

## Numerical results

Radii are km. The second and fourth numeric columns are direct rotating equatorial radii at 346.536369 Hz.

| Target mass (M☉) | Static RNS, 151 mesh | Rotating Req, 151 mesh | Static RNS, 196 mesh | Rotating Req, 196 mesh | ΔReq (196−151), km |
|---:|---:|---:|---:|---:|---:|
| 2.073 | 12.406102416 | 12.535316940 | 12.406615643 | 12.535416706 | +0.000099766 |
| 2.175 | 12.324738409 | 12.444654034 | 12.325323022 | 12.444887058 | +0.000233024 |
| 2.200 | 12.299531764 | 12.417136012 | 12.299531816 | 12.417323740 | +0.000187728 |
| 2.250 | 12.237556627 | 12.352626356 | 12.237380270 | 12.352711910 | +0.000085554 |

All eight static and eight rotating target roots passed direct RNS C-root checks. Static-radius comparison to F67 TOV stayed within 0.20 km. Every two-mesh rotating-radius difference was below 0.060 km; the largest absolute difference was 0.000233024 km.

## SHA-256 provenance from final run log

The successful run printed and archived a per-file manifest. These are the exact SHA-256 values printed by Actions. The raw MPA1 input is separately source-pinned and verified (value above).

| File | Bytes | SHA-256 |
|---|---:|---|
| `research/j0740/f62/f62_rns_precision_patch.py` | 1269 | `502e215d645193837e56ed866bcfd5f0bd0c6378f6f1b60ebc754bd2a9fd2934` |
| `research/j0740/f67/F67_MPA1_PCHIP_COLD_2p073_static_TOV_20261119.json` | 4340 | `811b6b9e3763e77df0e300f54cae0301cdac1cb1c285b09da8f32e23c0aa0dc8` |
| `research/j0740/f67/F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat` | 223209 | `d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22` |
| `research/j0740/f67/f67_mpa1_pchip_firstlaw_tov.py` | 14690 | `241e55855cb74edee59f45244eb613cc57042477e71dce06e518a96139553189` |
| `research/j0740/f68/f68_pchip_cold_rns.py` | 12068 | `6ba133b78536c98e8b9eb40d90b28389707078d5f9e12992338cbd44f7dde8f2` |
| `research/j0740/f68/test_f68_pchip_cold_rns.py` | 2269 | `aa739c8ce1fb138646bc573355bec0b9cba4fdf432df49f2361d1fc371d15eeb` |
| `results/F67/F67_MPA1_PCHIP_COLD_2p073_static_TOV_20261119.json` | 4339 | `53e044b9489160df600c8c21904fb304a28f6360bb4554b4272c0a639a066a99` |
| `results/F67/F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat` | 223209 | `13e35f7398d764f7e84046c927406807010d5e7617805c6a0a4e32b354e437e7` |
| `results/F68/F68_direct_RNS_result_20261119.json` | 81082 | `01c6780614c3b092dc01993d9087792cf016285ab7b895e2ec4e68109331cfe5` |
| `results/F68/F68_PCHIP_COLD_151pt.rns` | 13292 | `c79bad8756ff2b80e53d2cf0ff96d851f251a6f654d6e9b0a04fdedf175efacf` |
| `results/F68/F68_PCHIP_COLD_196pt.rns` | 17252 | `078a84efa6c07efe4c0a415e11564f700bf42fc56bed9a5249c6f2680cab3c90` |
| `rns-upstream/rns` | 230368 | `c4737a60547f3768f17d36e9da2822a71095fd65d1f41f1ca924e423252a084d` |
| `rns-upstream/rns.c` | 5389 | `4d737885b940879d6c9bf38a6254d60674b051fd66fc1b04e5e3ff042b9ec793` |

The [Actions run log](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44490729799) contains runner output and the printed checksums. Its artifact contains the machine-readable result JSON, RNS tables and `F68_SHA256_manifest_20261119.json` (121,581 bytes; GitHub-uploaded ZIP digest `3d252f9461d3b3dacf467b84047c4722950f3b2fb41c0512605653fbc747b1c9`; 30-day retention). This local sandbox could not re-download the ZIP, so the ZIP digest is GitHub's upload digest; per-file digests above are independently visible in the Actions log, not rehashed locally here.

## Execution history

Run [#44490504750](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44490504750) stopped at test discovery because the broad pattern also selected a different F68 test module requiring a helper unavailable in this merge checkout. The workflow now selects only `test_f68_pchip_cold_rns.py`; final run #44490729799 passed its six tests and completed all numerical gates. An earlier successful calculation is recorded in run #44488808013; final run #44490729799 reproduces the same radii with the per-file SHA output enabled.

## Current scientific limits

Still `NOT_RUN` / `NOT_ESTABLISHED`: physical EOS acceptance (including physical low-density matching and crust), native X-PSI likelihood, fixed-J stability, and the posterior/Bayesian update across the seven original EOS. F68 does not combine repeated NICER photons as independent likelihoods. F48–F51 and separate F52 work were untouched. F67 remains an alternative EOS diagnostic only.
