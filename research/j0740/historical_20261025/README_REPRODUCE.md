# J0740 EOS reproducibility package

## Status
The weighted-source analysis script previously ran successfully and processed 10,000 EOS draws. The 18-entry reproducibility ZIP passed its integrity test.

The three raw files used directly by the EOS update are now mirrored in private tenant-scoped artifact storage as a chunked bundle:
- 54 chunks under j0740/raw_bundle_parts/part-000 ... part-053
- Bundle size 222,910,037 bytes
- Bundle MD5 9fec0d9cd29df816bfea78565d0a6bb2
- Bundle SHA-256 5057752bec77b2417368fe144a6c1fc94203ce1eb15b975613a9ca334ddbfc2f
- Manifest: j0740/raw_bundle_manifest.md
- Reassembly and checksum script: j0740/restore_raw_bundle.py

The bundle contains the verified Salmi M-R sample archive, original weighted Miller source samples, and Legred PSR+GW+NICER EOS HDF5 file. It is stored as chunks because direct large-object transfers failed.

## Primary result (model-conditional)
R1.4 median 12.4051369 km (68%: 11.6702193–13.0279178); Lambda1.4 median 469.9656 (303.4738–603.9763); R(2.073 Msun) median 12.1257951 km (11.4231470–12.7350576); Mmax median 2.1951397 Msun (2.0796513–2.3917976); importance ESS 8884.995/10000.

## Remaining limitations
- The auxiliary Legred PSR+GW-only comparison file was checksum-verified during a later attempt but was not mirrored before the compute sandbox stopped.
- The exact effective source prior with the full rotating-star nuisance model and all hard support cuts has not been reconstructed by a prior-only run using the original X-PSI parameterization. Do not describe this as a complete exact event-level X-PSI reanalysis.
- The sandbox reported that no compute credit remained and could not be restarted, so the prior-only validation is still open.

The current result remains conditional on the Legred GP EOS prior and uniform-in-mass population model.
