# A01.01.51 / J0740 — F70: F68–F69 sayısal kontrol (19 Kasım 2026)

## Yeni kanıt / sınır

Bu çalışma F68'in özgün *MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL* EOS'unu ve F69'un ayrı *MPA1_PCHIP_COLD_FE56_SURFACE_V1_CONDITIONAL_NOT_ORIGINAL* EOS'unu **özdeş fiziksel model** saymaz. İki kaynak JSON SHA-256 ile sabitlenmiştir; kaynak dosyalar değiştirilmedi. Standart Python ile tekrar üretilebilir çapraz analiz; yeni GR/RNS yıldızı hesaplandığı iddia edilmez.

F68 iki uzaysal ızgaranın dönen yarıçap farkı 2.250 M☉ için **−1.180454 m**; fakat aynı iki koşuda gerçek raporlanan spin **346.745537343 Hz** ve **346.457411091 Hz**. Yani Δf = **−0.288126252 Hz**. Her iki sonuç önceki ±0.25 Hz hedef kapısı içindedir; ancak birbirine aynı dönme frekansında olduklarını söyleyemeyiz. F68 dönen iki-ızgara farkı yalnızca uzaysal ayrıklaştırma hatası değildir; spin uyuşmazlığı ayrı tutulmalıdır. 2.073 M☉ çiftinde Δf=+0.000241932 Hz ve ΔR_rot=−0.307555 m.

Dönmeyen iki RNS ızgarada spin=0 her iki koşuda, 2.250 M☉ yarıçap farkı **−3.681111 m** ve 2.073 M☉ farkı +0.807395 m: bu ayrım dönme frekansı uyuşmazlığından bağımsızdır. Aynı EOS baytlarını okumuş olmak, çözüm ağının ya da kök çözümünün sıfır sayısal hata taşıdığını kanıtlamaz.

F69 statik TOV ile F68 bağımsız statik TOV yarıçapları dört hedefte en çok **0.000497807 m** (0.498 mm) ayrılır; iki modelin düşük basınç sınırları farklıdır. F68 kaba statik RNS ile F69 bağımsız statik TOV arasındaki en büyük mutlak fark **4.768376586 m**. F69 P=0 Fe-56 dış tabakasının yarıçap katkısı en çok **2.452142650833413e−7 m** birinci mertebe tahmindir; bu kesin hata üst sınırı, mikrofiziksel doğrulama veya baryonik kütle ölçümü değildir. En büyük statik RNS ızgara farkı / Fe yüzey tahmini ≈ **1.50×10⁷** oranındadır, fakat fiziksel belirsizlik oranı olarak yorumlanamaz.

## Kabul kapısı

- Statik ızgara ayrımı **tespit edildi**, yeni statik GR çözüm iddia edilmiyor.
- Dönen ağ karşılaştırması **eş dönme frekansı kontrollü değil**; 2.250 M☉ eşlenmemiş f farkı 0.288126252 Hz.
- Sonraki RNS kabulü: aynı EOS giriş baytları, aynı hedef grav. kütle ve raporlanan |f−346.536369|<0.005 Hz, en az 3 uzaysal ağ ve kuvvetli yakınsama gözlemi; bu deney **henüz yapılmadı**.
- `original_MPA1_physical_acceptance=NOT_ESTABLISHED`; `F69_rotating_RNS=NOT_RUN`; `source_native_XPSI=NOT_RUN`; `seven_original_EOS_Bayes=NOT_RUN`.

## Tekrarlanabilir kanıt

Kaynaklar: F68 `F68_science_summary_20261119.json` SHA-256 `de2168c281ed90c975c5d658eb395cd88b3114c10e97d0137f181af61ab6f1be` ve F69 `F69_Fe56_conditional_surface_static_TOV_and_baryon_20261119.json` SHA-256 `4ffe44817f978b05f9888738ac4373cf345b959cac2c27cedebd93aa8dc7fb37`. Ana F67 kaynak EOS SHA-256 `d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22`; F68 RNS EOS SHA-256 `5af6e77740c3af282d30918e69a1794dab84895092209ac850c1e2ed2945ac16`.

Çalıştırma: `python f70_mesh_spin_crosswalk.py --f68 inputs/F68_science_summary_20261119.json --f69 inputs/F69_Fe56_conditional_surface_static_TOV_and_baryon_20261119.json --out F70_mesh_spin_crosswalk_20261119.json`.

Bağımsız kaynak kimliği, eşlenmiş kütle, fiziksel etiketleme, tam EOS Bayes iddiasını engelleyen başarısız-ol-kapalı testler: **9/9 PASS** (19 Kasım 2026; yerel Python). F70 çalışması yalnızca önceki ham sonuçların doğrulama/yorum düzeltmesi; otomatik gerçek yeni RNS hesabı değildir.
