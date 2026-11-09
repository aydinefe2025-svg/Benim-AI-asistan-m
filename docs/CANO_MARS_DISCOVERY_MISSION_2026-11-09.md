# CANO Mars Keşif Laboratuvarı — İlk tekrarlanabilir deney

**Gün:** 9 Kasım 2026 | **Durum:** Sentetik robot navigasyonu test edildi, birincil-kaynak sayısal mini-denetim çalıştırıldı. **Gerçek Mars keşfi/yaşam tespiti yok.**

**İş kimliği:** `topic_key=research.mars`, `goal_key=autonav-biosignature-evidence`, `acceptance_test=grid_route_battery_localization_and_primary_source_numeric_audit`.
**Kanonik görev:** GitHub Issue #493 — https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/493

## Birincil kaynak doğrulaması

| Kaynak | Gözlem | Yorum sınırı |
|---|---|---|
| NASA/JPL, **30 Ocak 2026**: [İlk AI-planlı sürüş](https://www.nasa.gov/missions/mars-2020-perseverance/perseverance-rover/nasas-perseverance-rover-completes-first-ai-planned-drive-on-mars/) | Perseverance, 8 ve 10 Aralık 2025 sürüşlerinde AI destekli rota noktaları kullandı | CANO'nun gerçek NASA algoritmasına eriştiği anlamına gelmez |
| NASA/JPL, **18 Şubat 2026**: [Mars Global Localization](https://www.nasa.gov/missions/mars-2020-perseverance/perseverance-rover/nasas-perseverance-now-autonomously-pinpoints-its-location-on-mars/) | GPS'siz Mars'ta bağımsız yer belirleme; uzun sürüşte biriken konum hatası | Bizim konum-hata artış katsayılarımız tamamen senaryodur |
| NASA/JPL, [Perseverance görev özeti](https://www.jpl.nasa.gov/news/press_kits/mars_2020/landing/quick_facts/) | 2021 iniş gününde tek yön ışık süresi ~11 dk 22 sn ve MMRTG güç kaynağı | `682 s` bir **tarihî referans**, bugünün ışık zamanı değildir; enerji modelinin Wh katsayıları gerçek rover telemetrisi değildir |
| Hurowitz vd., **Nature 10 Eylül 2025**, [DOI:10.1038/s41586-025-09413-0](https://doi.org/10.1038/s41586-025-09413-0) | Jezero/Bright Angel çamurtaşlarında organik-karbon izleri ve Fe-fosfat/Fe-sülfür birliktelikleri, **olası biyolojik işaretler** | Abiyotik yollar değerlendirilmiştir; Mars'ta yaşam saptandığı iddia edilemez |

## Çalışan deney: Arazide güvenli otonom rota

Simülatör `research/mars_rover_navigation.py` gerçek PDS haritası yerine **tamamen sentetik** 13×5 hücrelik bir ortam kurar. `.` normal, `s` kumlu, `#` geçilmez hücredir. Başlangıç `(0,1)` ve hedef `(12,1)` aynı kalır. Karşılaştırmada tek değişken kumlu arazi riskinin rota maliyetine dahil edilip edilmemesidir. Hücre 2 m, enerji tahmini 1 Wh/m, kuma girerken ×2,5, toplam 40 Wh bütçe ve 8 Wh korunmuş rezerv **örnek parametrelerdir**; Perseverance'ın ölçülen tüketimi değildir.

| Test ölçümü | Sadece adım sayısına odaklanan | Risk-ağırlıklı CANO rotası |
|---|---:|---:|
| Adım | 12 | 14 |
| Kumlu hücre | 9 | 0 |
| Mesafe | 24 m | 28 m |
| Tüketim (model) | 51 Wh | 28 Wh |
| Gerçek karar bütçesi 40 Wh - rezerv 8 Wh | **Geçersiz** | **Uygun (12 Wh kalan)** |
| Yerel otomatik yeniden konumlama | 1 | 1 |

**Sonuç:** 2 ek adımla hesaplanan enerji tüketimi 23 Wh düşüyor; güvenli rota 40 Wh zarfını sağlıyor. Kısa rota, 40 Wh zarfında kullanılmaya çalışılırsa enerji kontrolünden geçmez. Uygulama ulaşılmaz hedef, yetersiz enerji, konum hatası limiti, geçilmez hücre veya geçersiz haritada güvenli ret döndürüyor. Otonom kontrol varsayıldığı için 682 saniyelik tarihî tek yön gecikme her adımda Dünya'dan bir joystick yanıtı beklenmesi anlamına **gelmiyor**.

**Kısıt:** Planlayıcı küçük bir ızgarada mesafe + sentetik risk cezası minimize ediyor. Gerçek Mars arazi yükseklik, eğim, tekerlekte kayma, termal değişim, ışınım, iletişim penceresi, gerçek motor/fren dinamiği, gerçek sol süreleri, çoklu batarya/RPS gücü ve uçuş yazılımı içermiyor. Bulduğu rota fiziksel Mars görevine uygulanamaz.

### Yeniden üretim

```bash
python -m unittest discover -s tests -p 'test_mars_*.py' -v
python -m scripts.run_mars_rover_navigation
python -m scripts.run_mars_redox_evidence
```

Haricî hesap, internet, model API anahtarı ve ücretli hizmet gerektirmez. İsteğe bağlı `scripts/render_mars_route_comparison.py` yalnızca grafik üretir ve `matplotlib` ister; doğrulama için gerekli değildir.

## Birincil kaynak sayısal mini-denetimi (açık yayımlanmış değerler)

Nature makalesinde Apollo Temple'da Fe-S bakımından zengin bir ölçüm bölgesi için **yaklaşılan** değerler: Zn `2300 ± 670 ppm`, Ni `2000 ± 570 ppm`, Cu `419 ± 355 ppm`. Bunları **kesin aynı noktanın biyolojik imzası gibi birleştirmiyoruz**. `research/mars_redox_evidence.py` yalnızca `100 × aktarılan belirsizlik / aktarılan derişim` hesabını gerçekleştirir:

| Element | Belirtilen derişim / belirsizlik | Göreli aktarılan belirsizlik |
|---|---|---:|
| Zn | 2300 ± 670 ppm | 29,13% |
| Ni | 2000 ± 570 ppm | 28,50% |
| Cu | 419 ± 355 ppm | 84,73% |

Bunlar spektrumlardan yeniden türetilmiş değerler **değildir**. `±` ifadesinden biyolojik olasılık, istatistiksel sigma değeri veya yaşam keşfi çıkarılamaz. Tam PDS ham verisine dayalı tekrar analiz **ayrı kabul kriteri** olarak açık kalır.

## Test kapsamı ve kapanış tanımı

12 simülasyon + 3 sayısal mini-denetim, toplam **15 yerel stdlib `unittest` başarılı**. Kontrollü RED aşamasında kasıtlı boş simülatör 10 başarısızlık/7 hata vermiş, nihai gerçek uygulama aynı ana testleri geçmiştir. GitHub CI sonucunu ayrı doğrula, CI olmadığı sürece `ci_verified` yazma.

- **Gerçekleşen:** kaynaklı literatür taraması, sentetik güvenli rota, deterministik senaryo, programatik batarya/konum/hazard negatif testleri, yayımlanmış sayılara göre aritmetik denetim.
- **Açık:** Jezero PDS gerçek ham görüntü/spektrum üzerine yeniden üretim; fiziksel rover navigasyon/doğruluk kalibrasyonu; Mars'ta yaşam hakkında doğrulanmış bir sonuç. **CANO üretim veritabanının Render dış yedeği ayrıca P0 olarak açık; bu deney onu çözmez.**

Bu dosya deney makbuzudur; canlı üretim sistemi, gerçek rover, NASA veritabanı veya kullanıcı verisi üzerinde yazma yapılmadı.