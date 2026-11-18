# F44 — seven independently built F42 candidate EOS models at observed J0740 mass and spin

This stage invokes **the original pinned RNS full-GR C rotating stellar solver** with 7 different F42 candidate source-locked 200-node thermodynamic tables and asks for each EOS at **M=2.073 M_sun and f=346.536369 Hz**. Each root is a directly executed physical C-RNS model. The script explores finite central energy density and axis ratio with a bounded least-squares solver and retains failed evaluations. No interpolated star can substitute for the final direct solve. The initial central-density seeds are derived from separately independently solved and source-locked F43 static TOV stars. A second independent spatial mesh checks resolution and exact residuals; the RNS baryon M0 numerical field is deliberately not interpreted.

## What this is **not**

The seven F42 causal-lift/cold-gas models are NEW nonunique mathematical hypotheses, **not** the seven original JESTER nuclear EOS. WFF1 and WFF2 required nearly 20% source E changes. A static TOV first mass branch, a direct fixed-mass rotating model, or even sample-based mass turnback are NOT global stable branches nor evidence of microphysical validity. This task does NOT infer NICER radius or use F38 likelihood or provide Bayes factors. Treat every failed RNS output as `NOT_VALIDATED`, never as physical exclusion. `FINAL_SEVEN_EOS_BAYES=NOT_RUN` even if all seven numerical RNS roots pass.

## Pin chain

- JESTER exact native 7 source SHA locked in F42; F42 real Actions artifact ID `14412145963`, zipped SHA256 `c8d8cdc9804a702860ab1af65b60fa25dfac0f74fce9ec6347c4271ea3353115`, each source model `.rns` individual hash checked again.
- F43 26-node static TOV real roots and 12 source-locked regression tests; this file is consumed as numerical initial seeds.
- RNS original C commit `97e85d325a33e37f702306414533f6cd77812477` with output precision-only printf patch using existing `precise_apr4_mass_spin_root.patch_output_precision`, no GR equation changes.
- 151×301 and 201×401 independent GR C spatial grids.

## Gates

`fine_mesh.status=PASS` if and only if verified direct mass residual <=0.0015 Msun and spin residual <=0.05 Hz; report mesh comparison if source binaries both find root. If not all seven roots pass, F44 Actions has a failed scientific gate but machine-readable partial results and failure traces are uploaded for further repair. This is **numerical** acceptance only. Global physical EOS family acceptance, real Salmi X-PSI likelihood, and seven-EOS Bayes remain open.
