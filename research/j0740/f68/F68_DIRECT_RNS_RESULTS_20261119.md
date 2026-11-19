# F68 — F67 PCHIP-COLD direct RNS two-mesh diagnostic

**Run date:** 2026-11-19  
**Status:** `PASS_DIRECT_RNS_TWO_MESH_EXPLORATORY_ONLY`  
**Workflow run:** [44488808013](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44488808013)  
**Tested PR:** [#635](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/635)  
**Actions merge ref:** `aa585bffb1d041142fa1404d92839b37dd7a6c1d`  
**Feature head used:** `ec3a700df5e7423380c84d584f9c84c50c9c49ab`  
**RNS upstream revision:** `97e85d325a33e37f702306414533f6cd77812477`

## Scope

This run took the separately named F67 alternative numerical EOS, `MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL`, and solved static and uniformly rotating GR configurations with direct RNS C roots at 346.536369 Hz. Targets were 2.073, 2.175, 2.200 and 2.250 M☉ using 151- and 196-point meshes. It is an exploratory numerical gravity diagnostic; it does not certify a physical EOS or constitute the seven-original-EOS Bayesian analysis.

The original installed LALSuite 7.26.4 MPA1 table was source-pinned and verified in the run: SHA-256 `bd1b0c1a0506f37649275bfe401cf985f78b31e7d5dc3023665c49b9e2d0c3ec`. Six fail-closed table conversion tests passed. The output precision patch changed formatting only; the log records `physics_equations_changed: false`.

## Numerical results

Radii are km. The second table column is the direct rotating equatorial radius at 346.536369 Hz.

| Target mass (M☉) | Static RNS, 151 mesh | Rotating Req, 151 mesh | Static RNS, 196 mesh | Rotating Req, 196 mesh | ΔReq (196−151), km |
|---:|---:|---:|---:|---:|---:|
| 2.073 | 12.406102416 | 12.535316940 | 12.406615643 | 12.535416706 | +0.000099766 |
| 2.175 | 12.324738409 | 12.444654034 | 12.325323022 | 12.444887058 | +0.000233024 |
| 2.200 | 12.299531764 | 12.417136012 | 12.299531816 | 12.417323740 | +0.000187728 |
| 2.250 | 12.237556627 | 12.352626356 | 12.237380270 | 12.352711910 | +0.000085554 |

All eight static and eight rotating target roots passed the direct RNS C-root checks. Static-radius comparison to F67 TOV stayed within 0.20 km. Every two-mesh rotating-radius difference was below the 0.060 km acceptance limit; largest absolute difference was 0.000233024 km.

## Provenance and current limits

The [Actions execution log](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44488808013) records the full runner output, test results and per-target radii. The [Actions artifact](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44488808013/artifacts/14512292110) contains the machine-readable result JSON, tables and SHA-256 manifest (121,581 bytes; GitHub-uploaded ZIP digest `6e0e6c1bf6becbd3e45adfc4c9dbc27f80991cdcb70c33794a9811c8befa91c4`). Artifact retention is 30 days. The artifact archive was not independently downloaded and re-hashed from this restricted local environment; the ZIP digest above is GitHub Actions' upload digest, not a locally recomputed digest. Per-file manifest entries remain available inside the linked artifact.

Still `NOT_RUN` / `NOT_ESTABLISHED`: physical EOS acceptance (including physical low-density matching and crust), native X-PSI likelihood, fixed-J stability, posterior/Bayesian update across the seven original EOS. This F68 check does not combine repeated NICER photons as independent likelihoods. F48–F51 and separate F52 work were untouched. F67 remains an alternative EOS diagnostic only.
