# CANO-R1 — Birleşik 4DOF sanal CAD montajı (BETA)

**15 Kasım 2026** · yalnızca ücretsiz CPU hesaplaması ve salt-okunur doğrulama · **FİZİKSEL ÜRETİM / ROBOT HAREKET ONAYI YOK**.

## Bu paket neyi yapar?

Bu, geçmiş ayrı STL kutu/halka taramalarının tekrarı değildir. 6 parametrik **gerçek CSG/OpenSCAD katısı** (zemin tabanı, yaw rotor/şaft, üst kol, ön kol, bilek kolu ve pasif çeneli tutucu) aynı 4 eklemli koordinat sistemine bağlanmıştır. Her parça STL olarak ayrı kaydedilir; URDF kinematik ağacı ve üç duruşun GLB ön izlemesi oluşturulur. Önceki R1'in `CANO_R1_Continuous_STL_Offset_Certificate_2026-11-14.zip` idealize edilmiş silindir modeli ve 15 Kasım `CANO_R1_Contact_Force_Integration_2026-11-15.zip` ayrı, tarihli kaynak olarak kalır. Burada yeniden çalıştırılıp yeni sonuç sayılmadılar.

### Yeni geometri parametreleri

- Taban: 32 mm yarıçaplı ayak, 36 mm maksimum gövde yüksekliği; yeni yaw merkez yüksekliği **70 mm** (önceki basitleştirilmiş modelde 60 mm).
- Açılar: yaw ±120°, omuz −25°..100°, dirsek −145°..0°, bilek ±90°. Link1/2/3 nominal pivot arası **120/100/50 mm**.
- Linkler: Ø4.2 mm *varsayımsal* delikli, iç web boşaltmalı, ayrı STL'ler. Hareketli kol parçaları yerleşim için +7, −7, +7 mm y-ofset katmanlarına ayrıldı.
- Tutucu: sabit iki çeneli 23 mm'ye kadar uzanan CSG katı. **Mekanizması/aktüatörü yok**; ürün kullanılabilir tutucu değildir.
- Rotor ve gövde: arada 34 mm uzunlukta dar mil kesiti yer alıyor; **eğilme/burkulma/motor bağlantısı doğrulanmadı**.

### Ölçülmüş bilgisayar sonuçları

- `openscad` ile 6/6 ayrı STL dışa aktarıldı; mesh doğrulayıcı tümünü `watertight`, `consistent winding`, pozitif hacimli buldu. `results/estimated_plastic_masses.json` yalnızca **varsayımsal 1.250 kg/m³** plastik yoğunluğuna dayalıdır ve motor/dişli/kablo kütlelerini içermez.
- İlk yerleşimde 60 mm taban yüksekliğindeki gripper ucu zemine taşmış, eski START duruşu kabul edilmemişti. Yeni 70 mm pivot yüksekliği ve daraltılmış destek gövdesiyle revize edilen geometri test edildi. **Bu revizyon daha önceki dinamik tork sayılarının otomatik geçerli olduğu anlamına gelmez.**
- CSG montajın OpenSCAD bağımsız render dış sınırı ile Python FK dış sınırı 0.001 mm'den düşük sapmayla eşleşti.
- Yeni başlangıç → ara duruş: tüm sürekli parametrik zaman aralığında ve dört eklem için ayrı ayrı ±1° açısal sapmalarda; 2 mm hedefe göre **2.72589 mm sayısal korunumlu açıklık alt sınırı**, 131 geometri değerlendirmesi.
- Ara duruş → bitiş: aynı kapsamda **3.96665 mm sayısal alt sınır**, 129 değerlendirme. Bu kanıt yalnızca parça **dışbükey zarfları arasında ayrık olma** ve zeminden ayrıklık içindir; bağlantılı komşu parçaların temas/elektrik/mekanik fit uygunluğu kapsam dışında. İlerleme yolu doğrusal eklem aradeğerlemesi, zaman parametresi bu pakette belirtilmemiştir.
- Ø4.2 mm açık göbekli STL'nin dışbükey zarfı iç deliği doldurur. Test fikstüründe Ø3 mm pin ile poligonal yarıçap boşluğu yaklaşık **0.596 mm**; buna karşın dışbükey zarflar kesişir. Bu nedenle “hull overlap” tek başına gerçek katı teması kanıtlamaz. MuJoCo'nun dışbükey çarpışma yaklaşımı konusunda kaynak denetimini dikkate al.
- `tests/test_cano_r1_cad.py`: **17/17 yerel test başarılı**. Negatif kontroller arasında eski başlangıç pozunun reddi, açık yüzey/yön tersliği, sınırlı hesap bütçesiyle `inconclusive` dönme ve iş ucu görev toleransı kapısı bulunur.
- En önemli AÇIK görev: yeni START eski 60 mm'lik referansa göre yalnız eklem yeniden konumlandırılmasıyla 25 mm uç kayması yaratıyor; **70 mm pivot yüksekliği ek 10 mm düşey kayma** getirir. İş parçası koordinat toleransı kullanıcının görevine göre belirlenmedi. Hazır fiziksel uç konumu olarak kullanılamaz.

## Yeniden üretim (ücretsiz Linux / OpenSCAD)

```bash
# OpenSCAD CLI, Python >=3.11, numpy, scipy, trimesh gerekli
for part in base yaw upper forearm wrist gripper; do
  openscad -o "meshes/$part.stl" -D "part=\"$part\"" cad/CANO_R1_PARAMETRIC.scad
done
python generate_urdf.py
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 python build_evidence.py  # ön izleme için matplotlib
```

CI önerisi `github_workflow.yml` dosyasında; GitHub deposunda ayrı taslak PR olarak kabul edilmeden **CI doğrulandı** denemez. URDF içindeki örnek `effort` ve `velocity` sayıları uygulama uyumluluğu amaçlıdır, seçilmiş motor torku/hız kapasitesi değildir.

## Donanım kapısı neden kapalı?

`release_gate.py` gerçek motor tork-hız, baskı malzeme mukavemeti, toleranslı mil/yuva uyumu, gerçek aktüatörlü tutucu, kablo yataklar, görev toleransı, bağımsız tezgâh testi olmadan `physical_release_allowed=False` döndürür. Bunu değiştirmek, gerçek fiziksel kanıt gerektirir. **Üretim CANO çekirdeğine deploy yok, motor komutu yok, hücre/biyolojik malzeme yok.**

### Bilimsel ve teknik kaynaklar

- [OpenSCAD user manual](https://openscad.org/documentation.html) — CAD üretim aracı ve STL dışa aktarım dokümantasyonu.
- [URDF XML specification](https://wiki.ros.org/urdf/XML/joint) — eklem ağaçları, eksenler ve birimler.
- [MuJoCo computation docs](https://mujoco.readthedocs.io/en/stable/computation/) — dışbükey mesh temas varsayımları; MuJoCo bu pakette çalıştırılmadı.
- [CANO GitHub çalışma protokolü](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/blob/main/docs/CANO_CONTINUOUS_PROGRESS_PROTOCOL.md) — ayrık araştırma/CI ve üretim sınırı.

**Bağımsız Ruflo ajan yürütmesi yapılmadı.** Altı rol yalnızca metodolojik değerlendirme başlıkları olarak uygulandı: planlama, kaynak taraması, mühendislik, şüphecilik, tekilleştirme ve arşiv doğrulaması.