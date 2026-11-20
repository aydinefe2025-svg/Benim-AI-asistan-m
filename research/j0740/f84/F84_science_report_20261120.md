# A01.01.51 F84 — Original BPS vs distinct F83 Gibbs-phase overlap necessity audit

**20 November 2026.** This report addresses the actual F83 BPS-to-MPA1 *numerical alternative*; no physical EOS model is certified. F82/F83 C/RNS stars are not re-run or repurposed.

## Physical cold Maxwell/Gibbs requirement

For a zero-temperature single baryonic phase at fixed pressure, `mu=(epsilon+P)/n` is the Gibbs free energy per baryon, and `dmu/dP=1/n`. At a putative BPS→core transition P*, **mu_BPS(P*) must equal mu_core(P*)**; core should also be the lower-mu phase for all higher pressure in the overlap if only **one** transition is assumed. Physical density on increasing P is nondecreasing. Under these conditions native bracketing knots `(P0,n0,mu0)`, `(P1,n1)` yield the **interpolation-free** bound:

`mu0+(P*-P0)/n1 <= mu_BPS(P*) <= mu0+(P*-P0)/n0`.

Source exact BPS CSV SHA256 `a4195d48ae98fd64d0a9676891ccab5a5c035e713780ad1187e85571a98a1787` (130 rows) and F83 repaired numerical RNS EOS SHA256 `99fc172310b06b2aa0a972320478853c84057c6d1e2810328f97e3c19c37309d` (1213 rows) are immutable in the experiment. The selected previously published *numerical hybrid join* is `P*=0.07512275520519562 MeV/fm3`.

## Direct source-native outcomes (independent initial full-source crosscheck)

- Original BPS source neighbouring knot rows: `P0=0.072397332824260377`, `n0=0.0272 fm^-3`, `E0=25.688892037517`; `P1=0.076310910572544272`, `n1=0.0282`, `E1=26.635997445195386` in MeV/fm3.
- From the independent native full 130 source and first-law bound: `mu_BPS(P*) in [947.2028730345028,947.2064262030219] MeV`.
- F83 actual rebuilt EOS cold branch `mu_core(P*)=947.105593777567 MeV` with declared physical `mu_surface=930.4 MeV`. Thus under the specified normalization F83 does not meet Gibbs equality; the gap is at least `0.0972792569357 MeV`.
- At native highest BPS pressure `Pmax=0.36918421837903626 MeV/fm3`, source `mu_BPS=952.7997558931602 MeV`, while F83 core branch `mu_core=952.9047382508727 MeV` (BPS preferred, core higher Gibbs by `0.1049823577125 MeV`).
- Even **if** the arbitrary multiplicative core baryon normalization were adjusted to make `mu_core(P*)=mu_BPS(P*)`, the unchanged shape ratio `mu_core(Pmax)/mu_core(P*)` implies its `mu_core(Pmax)-mu_BPS(Pmax)` would still lie in `[+0.2028572573,+0.2064321819] MeV`. Thus a single stable BPS→that-core branch at exactly P* throughout this pressure overlap cannot be rescued by only renormalizing core n or mu0.
- All **52 original BPS source knots above P*** lie in the overlapping pressure domain. Source-native sign of core-minus-BPS chemical potential changes between native BPS pressures `0.2139781426132343` and `0.2199065268354509 MeV/fm3`. This is a *bracket for numerical evidence*, not a proven physical phase transition.

**Scientific interpretation:** This is a **conditional, interpolation-independent necessary-condition obstruction for the exact F83 candidate and the preselected join** given native BPS-source (P,E,n) and physically monotone n(P). It cannot exclude a different transition pressure, a new thermodynamically consistent inner crust, a corrected microscopic nuclear EOS, or a model whose μ0 normalization and source pressure–energy profile differ. Even original BPS source nodes have minute finite discretization inconsistencies: endpoint `mu(P1)-mu(P0)` differs from the monotone-n lower bound by ~`2.9e-5 MeV`. This is too small to remove the central ~`0.1-0.2 MeV` obstruction but must not be hidden.

**NOT_ESTABLISHED:** a physically consistent global crust–core EOS, original nuclear MPA1 admissibility, dynamic axisymmetric modes, full 7-model evidences. **NOT_RUN:** Salmi (2024) 12.9GB NICER/XMM original photon-level X-PSI nuisance-marginalized likelihood. A new physical EOS must be built and fully re-solved, not carry over F81–F83 stars.
