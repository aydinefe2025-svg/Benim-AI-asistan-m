# A01.01.51 — F67: MPA1_PCHIP_COLD_V1 yeni EOS temsili, soğuk birinci yasa ve iki bağımsız statik GR yıldızı

**Tarih: 19 Kasım 2026. Yeni deney, F58–F66 tekrarı değil.** Bu model, nükleer **özgün MPA1 değildir**; F42/F51 iyileştirmeleri veya özgün nükleer EOS etiketi altında sunulamaz. Model adı: `MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL`.

## Doğrudan fiziki giriş kaynağı

- LALSuite **7.26.4** kurulu paketinden alınan özgün MPA1 **102-satırlık basınç–enerji** tablosu; ham kaynak SHA-256 `bd1b0c1a0506f37649275bfe401cf985f78b31e7d5dc3023665c49b9e2d0c3ec` (F66 orijinal kaynak tablosuyla birebir).
- JESTER özgün MPA1 NPZ referansı `0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22`. Bu kaynağın 836 düğümlü **spline türevi** nükleer EOS tablosu ile aynı fiziksel temsil olduğu iddia edilmedi.
- Ham kaynak P,epsilon düğümleri değişmeden logP→logepsilon **PCHIP** biçiminde yeniden temsil edildi. F66'nın log-log kübik negatif-türev sorunu bu yeni hipotezde ayrı değerlendirildi; özgün LALSuite dosyaları, eski F58–F66 raporları değiştirilmedi.
- Geometrik birimler: P ve epsilon m⁻², yıldız R km, M Güneş kütlesi. Soğuk barotropik birinci yasa: `H(P)=∫dP/(epsilon+P)` ve `n(P)/n0=(epsilon+P)/(epsilon0+P0)·exp[-H(P)]`; başlangıç `n0=1` **keyfi normalizasyon**, µ0 ve fiziksel baryonik M0 **ölçümü değildir**.

## Yeni bağımsız statik TOV sonucu

İstenen hedef kütle **2,073 M☉**, özgün F61 LALSuite statik TOV yarıçapı **12.451544560 km**. Ayrı alternatif modelle doğrudan entalpi koordinatlı genel görelilik TOV denklemleri çözülerek **M=2.072999997 M☉, R=12.406155581 km**, merkez geometrik basınç **2.164961100184e-10 m⁻²** bulundu.

Yeni matematiksel EOS temsilinin tahmini statik yarıçapı, özgün MPA1 F61 statik yıldızından **-45.388979 metre** farklıdır (yaklaşık **45.39 metre daha küçük**). Bu, gözlemsel bir yarıçap değişim ölçümü veya hata çubuğu değildir; **iki farklı sayısal EOS hipotezinin model duyarlılığıdır**.

İkinci bağımsız `(u=r², v=m/r)` TOV formülasyonu *aynı merkez basıncında* M=2.072999342 M☉, R=12.406156613 km üretti. İki çözüm arasında |ΔM|=6.54341518e-07 M☉ ve |ΔR|=0.001032 metre, bağıl M farkı 3.1565e-07. Entegrasyon iç ızgara/kuadratürünün 12×32 ve 24×48 noktaları arasında aynı merkez basıncında ΔR=0.000315 metre; bu, bütün fizik model hatasının sınırı değildir. Yıldız yüzeyi çözümü EOS ham tablosunun en alt pozitif basıncında sonlandırıldı; gerçek P=0 yüzeyine ilişkin ek fizik sınırı vardır.

## Ses hızının bütün PCHIP kübik parçaları üzerinde ekstremum taraması

- Yeni EOS'ta yıldız merkez basıncına kadar **90 parçalı kübik aralık** işlendi. `c_s²/c² = exp(x-s(x))/s'(x)` [x=lnP, s=lnε]; türevin kritik noktaları `(1-s')s' - s''=0` dördüncü derece polinomundan bulunup sınırlarla birlikte sınandı: **36 iç gerçek kritik nokta**.
- PCHIP modeli içinde hesaplanan min–maks **3.72366688828e-12 – 0.730013765844**; incelenen model yıldızında negatif ya da ışıküstü `c_s²` yok. Ayrı 1.785 örnekli yoğun tarama da aynı sonuçla uyuştu.
- Bu, **yeniden oluşturulmuş sayısal PCHIP temsilinde kayan noktalı polinom köklerine dayalı kapsamlı ekstremum denetimidir**; nükleer madde geçişi, mikrofizik bileşim, faz kararlılığı, orijinal LALSuite EOS'un sürekli nedenselliği veya belirsizlik içeren fiziksel sertifika **değildir**.

## Testler, kaynak bütünlüğü ve kanıt

- GitHub PR **#631**, yeni ayrı F67 kodu, iki bağımsız statik GR TOV integratörü; **18/18 fail-closed yerel ve GitHub test**, son kod CI **3/3**. Ana gerçek CI `https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44481616029`.
- Orijinal kaynak SHA-256 yukarıda; sonuç JSON SHA-256 `811b6b9e3763e77df0e300f54cae0301cdac1cb1c285b09da8f32e23c0aa0dc8` (4340 bayt); alternatif termodinamik tablo SHA-256 `d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22` (223209 bayt); GitHub CI ZIP SHA-256 `283474708405323359eaf2e81083b3c6692f55b8b3517fde200cfd33692690ad` (98291 bayt), ZIP CRC **PASS**. İç manifestte sonuç ve tablo hashleri eşleşti.
- Baryon µ0 bağımsız olarak kalibre edilmedi; X-PSI'nin **orijinal foton ve nuisance likelihood** testi yapılmadı, **346,536369 Hz dönen RNS yıldızı bu ALTERNATİF modelle çalıştırılmadı**; yedi özgün EOS fiziksel kabulü ve tam, mükerrer-önselsiz Bayes sonucu **NOT_RUN**.
- Özgün F58–F66 verilerinin üzerine yazılmadı; **F67 ayrı** kaydedildi. Bu sonuçlar bilimsel denetim ve yeni araştırmalar için geçerli matematiksel model duyarlılık bulgusudur, nihai nükleer EOS keşfi değildir.

## Sıradaki gerekli fizik kapısı

F67 alternatif soğuk EOS'un gerçek düşük-P kabukla µ0/entropi faz sınırı, RNS doğrudan 346,536369 Hz yüksek çözünürlük ve kararlılık çözümü; ardından özgün NICER/XMM foton likelihood için bütün nuisance marjinalizasyonu ve çift sayımı engellenmiş yedi fiziksel EOS Bayes. Hesaplanmayan adımlar kapatıldı diye işaretlenmez.
