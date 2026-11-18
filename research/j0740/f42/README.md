# F42 — Seven explicitly NEW causal/first-law candidate barotropes

Scope: NOT a repair of the original named JESTER nuclear EOS, NOT astrophysical exclusion, NOT a full physical validation or a seven-EOS Bayes result. No source NPZ arrays are overwritten. New names end in `__CAUSAL_LIFT_FIRSTLAW_GAS_V1`.

The builder (a) fixes pressure nodes, (b) uses a one-sided minimal **energy-only lift** enforcing `e_{i+1}-e_i >= (p_{i+1}-p_i)/0.99`, (c) defines a piecewise-linear `e(P)` between each pinned source pressure knot, with exact sound-speed bound on each open segment, (d) extends below source lowest P to zero via explicit `e∝P^0.6` gas assumption, and (e) analytically integrates `dh=dP/(e+P)` and uses `n=(e+P)exp(-h)c²/(G m_b)` (units converted to cm^-3) anchored to a chosen rest baryon mass at the zero-pressure limit. The original source's `n` proxy is not silently trusted.

**This is a new, nonunique *hypothesis family*, not the original seven EOS.** The one-sided energy lift can significantly alter high-density stiffness. Independent TOV, Love, RNS, physical crust choice, baryon chemical potential suitability, whole-branch stability, mass/population prior and Salmi/X-PSI event likelihood are all open. Candidate formation itself cannot establish physically valid neutron-star matter. Record energy lift magnitude for every candidate. Reject claim of physical validation without the follow-up tests.

## Reproduce

In PR CI, fetch the exact seven JESTER lalsuite NPZs at commit `e6768650ce992abfd1153a6833857572fe5cd230` with the fixture `research/j0740/rotating_gr/fixtures/pinned_eos_center_fixture.json` (all SHA256s checked **before use**). Execute:

```
python -m unittest -v test_f42_causal_firstlaw_candidates.py
python f42_causal_firstlaw_candidates.py --source-dir ./source_npz --fixture ../rotating_gr/fixtures/pinned_eos_center_fixture.json --out ./candidate_outputs
```

Every resulting 200-row `.rns` table and its source provenance SHA is emitted under its new label. If any source missing, SHA changes, EOS invalid or output nonmonotone, fail closed and keep partial report. Output `F42_candidate_build_report.json` keeps `TOV_RNS_and_EOS_Bayes=NOT_RUN` regardless of successful candidate construction. The pipeline explicitly avoids 12.9GB NICER / 40MB Salmi re-downloads.
