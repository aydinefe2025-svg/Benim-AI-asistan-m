# F68 — direct RNS rotation diagnostic for F67 PCHIP cold EOS

This work follows the next open computational gate recorded in Notion and in
GitHub Issue #280: feed the separately named F67 `MPA1_PCHIP_COLD_V1` table to
the pinned relativistic RNS C solver, calculate fixed-spin roots at 346.536369
Hz over 2.073–2.250 solar masses, and compare 151- and 196-point EOS tables.

It does **not** validate original MPA1 or complete the EOS posterior. The F67
table begins above vacuum; the cold baryon density normalization remains
arbitrary. The RNS output is therefore a gravity-only numerical diagnostic.
The code does not interpret baryonic mass, fixed-J stability, native X-PSI
likelihood, or Bayes evidence.

GitHub Actions reruns F67 from the source-pinned LALSuite 7.26.4 raw MPA1 table,
checks the generated thermodynamic table and static result against existing
SHA-256 receipts, then performs direct RNS C roots at each target mass and mesh.
Every reported star must be an actual C-solver evaluation. Acceptance requires
static RNS/TOV radii within 0.20 km and 151/196-point rotating radii within
0.060 km. The artifact contains root traces, both meshes, hashes, and failure
records even if a numerical gate fails.

Workflow: `.github/workflows/j0740-f68-pchip-cold-direct-rns.yml`

Command used by CI:

```sh
python -u research/j0740/f68/f68_pchip_cold_rns.py \
  --source "$SOURCE" --rns rns-upstream/rns --out-dir results/F68
```

Final scientific scope remains limited to the F67 alternate numerical EOS.
Source-native X-PSI nuisance marginalization, physical EOS admission, and the
seven-original-EOS Bayes calculation remain open.
