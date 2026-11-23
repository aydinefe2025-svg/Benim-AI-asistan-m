# F140 — Derived cold crust seam, six original EOS source checks

F139 found an original C-backed LAL interpolant's negative cs² near pressure knot 254 in six non-APR4 EOS. F140 **does not modify the seven original EOS or call any repair original nuclear physics**. It proposes separate *derived numerical tabular EOS*, each bridging the full bad interval.

The exact local cold bridge sets epsilon(P)=epsilon_L+s(P-P_L), with s=(epsilon_R-epsilon_L)/(P_R-P_L)>1. It follows cs²/c²=1/s in (0,1). For n_L from native LAL, n(P)/n_L=[(epsilon+P)/(epsilon_L+P_L)]^(s/(s+1)). Hence mu=(epsilon+P)/n and log(mu/mu_L)=integral dP/(epsilon+P), so the first law is exact **inside the analytic bridge**. Boundary pressures and energies are continuous, but high-side native baryon normalization / Gibbs phase preference and global star-domain EOS remain **unproven** and are explicitly measured, not assumed.

Real GitHub Actions checks original 7 NPZ SHAs and upstream commit, invokes pinned LALSuite 7.26.16 C APIs, writes the six new 2-col geometrized (m^-2) EOS candidates, re-reads via C, tests local derivative over 1537 pressure points including outside the seam, and measures native mu/h mismatch. Failures are retained as artifacts.

**Acceptance ceilings**: local numerical and cold-law gate only, never physical seven-EOS certification, never full M-R posterior or photon likelihood, never dynamic rotating stability. Source-native F139 2695 previous calls, F134-F138 original APR4 sequence, and earlier 323 stars are not repeated. 