# CANO — Arşivlenmiş keşifleri gerçek tasarım kararına bağlama

**11 Kasım 2026; konu:** `cano.core` + `organism.digital` + `research.robotics`, yazılım deneyi. Mevcut [CANO PR #538](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/538) üzerinde yeniden kullanım, ikinci benzer koloni yaratma değil.

## Arşiv → doğrudan kullanılan karar

| Önceki araştırma | Kaynak / arşiv | Bu değişikliğin gerçek kullanımı | Aktarılmayan yanlış çıkarım |
|---|---|---|---|
| Piezoelektrik rezonatör: en iyi sayısal çalışmada 0,42 mW tepe | [Makale](https://doi.org/10.1038/s41598-026-60480-3), [Notion #25](https://app.notion.com/p/4092bd61682a819880bbff1edd19f835) | `electric_peak_mw`, sadece iyimser hesap | Sürekli saha elektrik üretimi kanıtı değil |
| Terle çalışan mikrobiyal yakıt hücresi: yapay terde 20,29 µW/cm² | [Makale](https://doi.org/10.1016/j.jpowsour.2026.240856), [Notion #22](https://app.notion.com/p/4092bd61682a81a79a43f4928a9f32e1) | Örnek alan 10 cm² için 0,2029 mW optimistik ölçeklendirme | Gerçek insan üzerinde 24 saatlik net çıkış değil; evde mikrobiyal deney planlanmadı |
| Termopnömatik yumuşak robot, hareket üretimi | [Makale](https://doi.org/10.1038/s41467-026-77422-2), [Notion #25](https://app.notion.com/p/4092bd61682a819880bbff1edd19f835) | Mekanik iş olarak sınıflandırılır, elektrik hesabına eklenmez | Gösterimde ısı tabancası kullanımı açıklandı; pasif her-koşul kullanım varsayılmadı |
| Tesla 1888 patentli döner alan düzeni | [US381968A](https://patents.google.com/patent/US381968A/en), [Notion tarih dizini](https://app.notion.com/p/40a2bd61682a81c8a078ccea752cb76b) | Elektrik aktarımı / motorlaştırma ayrı, hasat kaynağı değil | Yoktan enerji kaynağı olarak sayılmadı |
| Daha önceki CANO adaptasyon testi | [Doğrulama raporu](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/blob/main/research_reports/organism-lab-adaptation/validation-2026-11-08.json) | `adaptation_demonstrated=false` ilerleme iddiasını durdurur | Dijital organizma sayısı = gerçek genel öğrenme değildir |
| Üç kohortlu bileşim aktarım deneyi | [Issue #413](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/413), ChatGPT Library `CANO_COMPOSITION_TRANSFER_2026-11-08.md` | `compositional_transfer_confirmed=false` ilerleme iddiasını durdurur | 450 simülasyonun bazı pozitif alt metrikleri, önceden tanımlı kabul kapısını geçmedi |

Daha önceki [Orchard ajan araştırması](https://app.notion.com/p/4092bd61682a81a79a43f4928a9f32e1) görev/işçi ile değerlendirme ortamını ayırmaya işaret ediyor. Burada yeni çalışan ağ ajanı yaratılmadı; test/çalışma ayrımı korundu. Mevcut [Neon/Render veri koruma protokolü](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/95) sebebiyle canlı ortama dokunulmadı.

## Çıktı — birimleri karıştırmadan

`python -m scripts.cano_seed_lab_demo` önceki sanal sonuçların yanına `research_reuse` alanını ekler. Böylece önceki basit 44 kredi hesabı ile gerçek araştırma **mW/mWh** bilgileri aynı çıktı içinde, fakat birbirine dönüşmüş gibi sunulmadan tutulur.

- Örnek: 0,42 mW (sayısal tepe) + 20,29 µW/cm² × 10 cm² = **0,6229 mW** *farklı yayınlardan iyimser toplam*.
- 24 saat boyunca bu iki tepenin birlikte sürmesi varsayılsa bile en çok **14,9496 mWh** (bu seçili değerlerden türetilen senaryo; fiziksel, evrensel üst sınır değil).
- Örnek sensör görevi: beklemede 0,05 mW, %1 görev süresinde 1 mW → **0,0595 mW ortalama**, 24 saatte **1,428 mWh**. Üstteki araştırma değerleriyle *kağıt üzerinde adaya benziyor*, **sahada doğrulanmadı**.
- Örnek 3 W sürekli bilgisayar: 24 saatte **72.000 mWh** → bu **iki** hasat yaklaşımıyla, hatta seçili ideal tepe kabulüyle bile **yetersiz**.
- Dolayısıyla önce ölçülebilir düşük güç sensör düğümü veya seyrek çalışan telemetri; bilgisayarı besleme iddiası yok.

## Uygulama ve sınamalar

- `data/cano_research_bridge_evidence.json`: birimleri, birincil bağlantıları, Notion kaynaklarını, kanıt türünü ve çalışma sınırlarını açık tutan salt-okunur katalog.
- `core/archived_energy_bridge.py`: Decimal tabanlı güç/enerji hesabı, kaynak seçimi, elektrik transferini/termal aktüasyonu elektrik hasadından ayırma, kabul kapısı.
- `tests/test_archived_energy_bridge.py`: kaynak saklama, güç/alan dönüşümü, yüksek güç ret kararı, değişmez saha garantisi sıfır, negatif/NaN/duty hatası, önceki başarısız adaptasyon kapısı, mevcut demo çağrısı.
- `scripts/cano_seed_lab_demo.py`: geçmiş araştırma kararları doğrudan mevcut simülasyon çıktısına eklenir.

**Yerel RED:** Başlangıç 8 yeni test `NotImplementedError` ile FAIL, sonra eksik koşum raporlaması testi FAIL; **GREEN:** 19/19 toplam test (önceden 10 + yeni 9), Python 3.13, `python -m unittest discover -s tests -v`; `python -m scripts.cano_seed_lab_demo` JSON okundu.

**Sınırlamalar:** Çalışma araştırma kayıtlarının kullanımıdır, kaynak makalelerin birincil tam metin/ham verilerini bağımsız tekrar inceleme değildir. Buradaki katalog gerçek zamanlı sensör telemetrisi değildir. Farklı yayınların tepe sayıları bir arada gerçek dünyada ölçülmedi; sistem `field_guaranteed_mw=0`, `proven_feasible=false` tutar. `SHA-256` imzalı harici kurtarma yedeği değildir. Kendi kendini internette çoğaltan kod, canlı LLM işçisi, fiziksel robot ya da ticari ürün yok.

**Bir sonraki kabul testi:** Ölçülmüş saatlik ışınım / titreşim / yük altındaki güç / depolama verimi ile 24 saatlik gerçek mWh hesapla, sonra boşalım ve saatlik görev kuyruklarını karşılaştır. Yalnız kaynak ve ölçüm kanıtı geldikten sonra güç planlama otomasyonu. Önce güvenli ve bağımsız gerçek CANO yedeği P0 sürecek.
