# CANO — Daha az zorunlu kayıpla genom seçilimi: sabit kural deneyi

**Tarih:** 9 Kasım 2026 · **Topic:** `organism.digital` · **GitHub:** Issue [#413](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/413) · **Sınıflandırma:** sınırlı, deterministik, fiziksel olmayan simülasyon. **Üretim / PostgreSQL / günlük genom checkpoint'i değiştirilmedi.**

## Bilinen sorun ve yeni çalışma

[PR #442](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/442) ile yararlı A+B genomunun yayılabildiği ama sabit 12 kişilik kapasiteyi her adımda zorla boşaltmanın ortalama ~80 kayıp ve yeni doğum gerektirdiği gösterildi. Bu rapor **farklı bir mekanizmayı** inceler: kapasite doluyken rastgele ve fenotipten bağımsız bir kayıp, her adım yerine yalnız **4. adımlarda**; `eligible` seçeneğinde ek olarak gerçekten bölünebilecek enerjisi olan bir birey bulunmalı. Zorla kayıp yine gerçek bir sanal ölümdür; bedelsiz, etik/gerçek yaşamda uygulanabilir bir politika değildir.

Eski `digital_vm.py` (`0ced308713956ebd43fa58ef29bb31502101d001`) ve `resource_competition.py` (`de430c7a2cf971a1cf1105c3f218c86ea3a251f5`) **birebir korunur**. Yeni `low_loss_turnover.py` araştırma alt sınıfı dört politikayı sınar: `closed`, `continuous`, `paced`, `eligible`. Tüm politikalar dönüşümlü kaynak dağıtımı kullanır. `closed` ve `continuous` yeni uygulamada önceki `rotation_closed` ve `rotation_turnover` referansıyla birebir eşleşmesi açısından regresyon testinden geçirilmiştir.

### Önceden belirlenmiş deneme düzeni

* İki yeni 30'luk bağımsız başlangıç tohum grubu: **800..829** ve **900..929**. Daha önceki #442'nin 600/700 tohumları tekrar kullanılmadı.
* Her tohumda 4 politika × 3 görev maliyeti (0, **1**, 2) × (ödül 2 / ödül 0 kontrol), 80 adım, A/B ortamı her 12 adımda değişir: **1440** sınırlı simülasyon, ayrıca 60 bölünme-kapalı kontrol koşusu.
* 12 bireylik sabit nüfus kapasitesi, adım başına 1 kaynak, başlangıçta araştırmacı tarafından konmuş **4 A + 4 B + 4 A+B** genom, **mutasyon 0**. Bu koşullar yeni gen keşfi ya da gerçek AI öğrenmesi kanıtı olamaz.
* Önceden ilan edilen **ANA MALİYET = 1**: `eligible` ve `closed` arasındaki ödül−ödülsüz nedensel A+B genom payı farkı. Her 30'luk grupta tohumların >=%50'sinde pozitif fark; tek yönlü kesin işaret testi p<.05; eşleştirilmiş farkın yaklaşık %95 alt sınırı >0; `eligible` zorunlu kayıp ortalaması `continuous`un <=%50'si, AB payı kazancı da `continuous`un >=%50'si; tüm negatif kontroller doğru. Gruplardan herhangi biri geçmezse **genel kabul FAIL**.
* Maliyet **0** seçilim için *duyarlılık/keşif* koşuludur; maliyet **2**, ödül ile maliyetin net enerji açısından sıfırlandığı **sıfır-net negatif kontrolüdür**. Bu iki seviyeden ana kabulün kazananı seçilemez.

## Doğrulanmış deney verisi

| Metrik (80 adım) | 800..829 | 900..929 |
|---|---:|---:|
| **Birincil maliyet 1**: `eligible` daha iyi, eşit, daha kötü | 0 / 30 / 0 | 0 / 30 / 0 |
| Birincil maliyet 1: nedensel AB payı ortalama fark | **0.0000** | **0.0000** |
| Birincil maliyet 1: kesin işaret testi | p=1 | p=1 |
| Birincil maliyet 1: `eligible` zorunlu kayıp ortalaması | 2.767 | 2.700 |
| Birincil maliyet 1: `continuous` zorunlu kayıp ortalaması | 4.400 | 4.233 |
| **Ana bilimsel kabul** | **FAIL** | **FAIL** |
| Keşif maliyet 0: `eligible` daha iyi /30 | 30/30 | 30/30 |
| Keşif maliyet 0: `eligible`−`closed` nedensel AB payı ortalama farkı | +0.3778 | +0.3944 |
| Keşif maliyet 0: `continuous`−`closed` farkı | +0.3861 | +0.4500 |
| Keşif maliyet 0: `eligible` zorunlu kayıp ortalaması | **17.500** | **18.133** |
| Keşif maliyet 0: `continuous` zorunlu kayıp ortalaması | **71.667** | **70.900** |

Maliyet 0 altında `eligible`, sürekli boşaltmanın sanal zorunlu kayıplarını sırasıyla **%75,6 / %74,4 azaltırken**, onun toplam seçilim kazancının yaklaşık **%97,8 / %87,7'sini** korudu. Bu maliyet seviyesi **ana kapı değildir**: yalnızca ücretsiz görev koşullarında yapılan bu gözlemle, gerçek enerji maliyetinde iyileşme iddia edilemez. Maliyet 1'de her iki 30'luk grupta bütün ana farklar tam 0'dır. Sonuç ``üstün yöntem bulundu'' değil, **görevin net enerji maliyeti başarıyı belirliyor** şeklinde sınırlandırılmış hipotez desteğidir; tek kök neden kesinleşmedi.

Maliyet 2 kontrolünde ödüllü/ödülsüz izlemler, son genom sayıları ve zorunlu kayıp sayıları birebir aynı. Bölünme kapalı tüm kontrol koşularında doğum 0. Başlangıç A/B/AB kurucu genomlar kalıtsal ama **mutasyon kapalı**, dışarıdan komut/ajan/robot/LLM çağrısı yapılmadı. Eşleştirilmiş normal güven aralıkları *sentetik deterministik tohumlara* ilişkin betimsel ölçüdür; gerçek dünya belirsizliğinin istatistiği değildir.

## Test, saklama ve bilimsel sınırlama

* İlk deney testi, yalnızca iskelet alt sınıf varken beklenen `NotImplementedError` ile **RED** oldu; uygulama sonrası **8 yeni + 11 önceki = 19/19 lokal test GREEN**. Referans motorun hash ve adım adım davranış eşleşmesi ayrıca doğrulandı.
* Yeni modül `organism_lab_cloud/organism_lab/low_loss_turnover.py`, test `organism_lab_cloud/organism_lab/tests/test_low_loss_turnover.py`. Rapor dosyalarında iki 30-tohum × 24-kol sonuç ayrıntısı; gövde SHA-256 ve bağımsız deterministik hesaplama ile aynı dosyanın tekrar yazılması ve bozuk/sahte hash reddi denetlenir.
* `.github/workflows/cano-low-loss-vacancy-evidence.yml` gerçek kaynak kodundan Python 3.11 ve 3.12'de tüm örneklemleri yeniden üretip rapor gövdesi ve dosya SHA-256'sını `research_reports/organism-lab-low-loss/EVIDENCE_MANIFEST.json` ile karşılaştırır. CI tamamlanmadan başarılı diye etiketlenmez.
* `research_reports/organism-lab-low-loss/low-loss-seeds-800-829.json`: **gövde** `71d8c9ebc03ad6502a9926162ac70c575c4b4cb0a0ca1846487117f6d24231c8`.
* `research_reports/organism-lab-low-loss/low-loss-seeds-900-929.json`: **gövde** `19519b73df9a2cd6c99cf44c16e79ea3263e3c1daee26a2be96bd955847aad18`.
* Ana kütüphane hedefi: `/Research-Evidence/Organism-Lab-2026-11-09/Low-Loss-Vacancy-413/`. GitHub Issue #413 açık kalır; hiçbiri üretim güncellemesi değildir.

**Sonraki deney (henüz uygulanmadı):** Maliyet 1 ortamında görev ödülü, bakım maliyeti, daha uzun görev periyodu ve kaynak dağıtımı etkileşimlerini *önceden belirlenmiş* sabit tasarımla ayırmak. Eğer gerçekten yeni yararlı mutasyonun oluşumunu ölçmek isteniyorsa başlangıçtaki mühendislik ürünü A+B genomunu çıkarıp sıfırdan evrilme kontrolünü yeni çalışmada sınamak gerekir. Tek ölçüt yalnız nüfus ve zorunlu kayıp sayısı olamaz. Güvenlik: gerçek sistemi otomatik öldürme/çoğaltma politikasına bağlama.
