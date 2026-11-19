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


## 2026-11-19: Actions ile tarihsel sonucu yeniden üretme (yeni posterior değil)

GitHub Actions run [#44321341032](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44321341032) başarıyla tamamlandı; 8/8 iş adımı, kaynakları indirme ve SHA-256 hesaplama, tarihsel KDE-to-KDE betiğini çalıştırma, SHA manifesti üretme ve artifact yükleme PASS. Workflow commit: `45262d5d60a884c33b19b61be75e5af87a0030e8`. Artifact #14436225742 (`j0740-historical-legred-reproduction-20261118`), 5,403 bayt, GitHub artifact SHA-256 `c774c5788897b8c1cfdc12e2c4972fc500db5872311e766648fc223065f5ec59`.

İçerik kontrolü tamamlandı: ATL’deki özgün paket 54/54 parçadan yeniden akışla birleştirildi; 222,910,037 bayt, MD5 `9fec0d9cd29df816bfea78565d0a6bb2`, SHA-256 `5057752bec77b2417368fe144a6c1fc94203ce1eb15b975613a9ca334ddbfc2f`; kayıtlı manifestle tam eşleşti. Bu, yalnız boyut kontrolü değil, içerik hash doğrulamasıdır.

Actions, özgün Zenodo kaynak dosyalarını indirip yayınlanmış boyut ve MD5 değerlerini doğruladı; yeni hesaplamanın SHA-256 değerleri: Salmi 2024 `1549467c64a8801c39213bd28c89737d087cc5ab7a70da1d8d3a32b2d09185c8`; Miller 2021 `125cee5208d31c25791023e84e020362df56ad3ef808e8b325f57c2be65a79e2`; Legred 2021 `39ff1308fb2461eddaf82525ec8581db554c0d3907431ba7d23a04f4621b5abe`.

Hesaplanan tarihsel KDE-to-KDE özetleri, 25 Ekim'de kayıtlı sonuçla toleranslar içinde eşleşti: R1.4 medyan 12.405136853361064 km (fark 1.78e-15 km); Λ1.4 medyan 469.9656192710668 (fark 3.41e-13); Mmax medyan 2.1951397491135327 M☉ (fark 0); R(2.073) medyan 12.125795126927729 km (fark 3.55e-15); ESS 8884.995132019996/10000 (fark 2.73e-11). Bu, tarihsel model-koşullu sonuç için yeniden üretilebilirlik kanıtıdır; yeni posterior veya nihai fiziksel EOS Bayes sonucu değildir.

NICER verisi iki kez çarpılmadı: tarihsel pipeline, Legred içindeki eski J0740 terimini Salmi 2024 kaynak posterior oranıyla bir defa değiştirir; Miller örnekleri kaynakposterior yoğunluğu KDE düzeltmesinde kullanılır. X-PSI foton-seviyesi likelihood/marjinalizasyon `NOT_RUN`; fiziksel olarak doğrulanmış nihai EOS Bayes `NOT_ESTABLISHED`. F52 WFF1 ayrı görevdir.
