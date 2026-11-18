# A01.01.51 — F64: Özgün MPA1 EOS'ta n-sütunu birinci-yasa sapması ve doğrudan C/RNS kontrollü deney

**19 Kasım 2026 | Yeni ve kaynak-kilitli sayısal hesap; özgün EOS'un nihai fiziksel kabulü veya yedi-EOS Bayes sonucu değildir.**

## Hangi eksik kapatıldı?

F63'ün **bayt düzeyinde doğrulanmış, 196 düğümlü özgün MPA1 kaynağından türetilmiş RNS EOS tablosu** (`SHA256=15cd0e83830635fe46264ff5e5c52f97f4b8846dc73c1a64768e1237417d9e51`) için baryon sayı-yoğunluğu `n` sütununun, enerjiyi doğrudan sabit ortalama parçacık kütlesine bölerek üretildiğini doğruladık (`n/rho ≈ sabit`). Bu yaklaşım soğuk barotropik bir EOS'un **d ln n = d epsilon / (epsilon+P)** birinci-yasa ilişkisini genelde sağlamaz.

Kaynağın **basıncı (P), enerji yoğunluğu (epsilon), entalpisi (H) değiştirilmeden**, yalnız n(P) 64-düğümlü Gauss-Legendre integrasyonuyla yerel log-lineer epsilon(P) varsayımı altında yeniden kuruldu. Düşük basınçtaki ilk düğümde **n değerini eski sütuna eşit sabitleme tamamen keyfi referans normalizasyonudur**; fiziksel baryon kimyasal potansiyelinin belirlenmesi değildir. 32/64/128 düğümlü integrasyonların maks. göreli farkı `1.44e-14` ve doğrusal epsilon(P) için analitik integral birim testi geçti.

| Boyutsuz n kaynak / birinci-yasa n − 1 | Sonuç |
| --- | ---: |
| En alt basınç referans düğümü | ~0 (tanım gereği) |
| F62/F63 gözlenen 2.073 M☉ yıldız merkez yoğunluğu, `1.0153663088666426e15 g/cm³` | **+13.913411%** |
| F63 sabit-J tepe merkez yoğunluğu, `2.102e15 g/cm³` | **+41.904554%** |
| Tablo üst basınç düğümü | **+53.953072%** |

Bu oranlar **baryonik kütle düzeltmesi** değildir: birinci yasa içindeki n(P) şekil farkını, aynı keyfi düşük-basınç referansına göre gösterir. Ayrıca kaynak H tablosunun uç değeri aynı log-lineer epsilon(P) altında yeniden entegre edilen H'nin yaklaşık **%0.2564** üzerinde; bu da bütünüyle fiziksel olarak tutarlı soğuk EOS'un bağımsız kanıtının bulunmadığını gösteren ayrı bir temsil farkıdır.

## Yeni fiziksel C/RNS deney sonucu: yalnız n sütunu değiştirildi

Aynı upstream `rns-alberta/rns` C genel görelilik çözücüsünde, aynı `MDIV=151, SDIV=301` uzaysal ızgarada, aynı `rho_c=1.0153663088666426e15 g/cm³` ve istenen f=346.536369 Hz değeriyle, **iki gerçek doğrudan yıldız** yeniden çözüldü. C fizik denklemleri değiştirilmedi; yalnız `printf` ile M, R_eq, f, M0 ve J beraber yazdırıldı.

| RNS C çıktısı | Özgün n=e/m_avg yaklaşımı | Birinci yasa ile n(P), alt referansı keyfi |
| --- | ---: | ---: |
| Gravitasyonel M (M☉) | 2.073000000 | 2.073000000 |
| R_eq (km) | 12.533295930 | 12.533295930 |
| f (Hz) | 346.614535610 | 346.614535610 |
| J (g·cm²/s) | 6.10431039899 × 10⁴⁸ | 6.10431039899 × 10⁴⁸ |
| **RNS M0 (M☉)** — *fiziksel olarak kalibre edilmemiş* | **2.560814055** | **2.402956565** |

Böylece *RNS'nin yazdırdığı hassasiyette* M, R, f, J değişmedi; **M0 çıktısı −0.157857490 M☉ (−%6.164348)** değişti. **Birinci yasa integrasyonu n'nin bağıl şekil tutarlılığını iyileştirir; RNS M0 değerini fiziksel baryonik kütleye dönüştürdüğünü kanıtlamaz.** Bu kontrollü deney, F63 kütle–J geometrik dönüş noktasının n-normalizasyonundan ayrı değerlendirilmesini destekliyor, ancak bütün EOS'un nedenselliğini veya küresel kararlılığını ispatlamıyor.

## Bağımsız kabul kanıtı ve sınırlamalar

- Kaynak RNS tablo SHA-256 F63 ile birebir eşleşti; orijinal JESTER NPZ bilinen SHA `0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22` soy ağacı korundu. Kaynak düşük-basınç negatif cs² düğümü #254 / enerji monotonluğu sorunu hâlâ çözülmüş **değil**; 196 düğümlü yeniden örnekleme özgün fizik tablosunu otomatik olarak iyileştirmez.
- GitHub PR #625: `https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/625`; ilk gerçek C/RNS CI `https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44402339869`: **14/14 test**, upstream C derlemesi, iki gerçek RNS yıldızı ve fizik etiketi/önsel kontrolleri başarılı. Üç GitHub kontrolü yeşil.
- CI ZIP SHA-256: `30fc9ed245dbfa2caa94ba96670fb1dd5102f0867cc832fd559629a2c80335cc`, ZIP CRC iyi. İçerideki gerçek sonuç JSON SHA-256: `033344658ef0784ecff58ae60d6cb317c70dcca9df5bc7d1f0c1d0a6aa51ad7a`; manifest ile üyelerin SHA-256 eşleşti. Ham JSON ve iki kaynak türevi EOS dosyası kaydedildi.
- **Önemli açık işler:** fiziksel referans baryon kimyasal potansiyeli/mu0, gerçek özgün düşük-basınç LALSuite kabuk geçişi, E(P) ve H(P) ortak ilk-yasa tutarlılığı, küresel kararlılık, X-PSI özgün foton+nuisance likelihood, mükerrer foton sayımı yapılmadan yedi *özgün* EOS Bayes posterioru. Bunlar `NOT_ESTABLISHED` / `NOT_RUN` olarak kalır.

**Yorum:** F64 özgün MPA1'in n-proxy sütunu belirsizliğini sayısallaştırıp RNS'de hangi çıktının bundan etkilendiğini gerçek C koşularıyla ayırdı. **Yedi özgün EOS'un fiziksel kabulü ve nihai gözlemsel kazananı belirlenmiş değildir.**
