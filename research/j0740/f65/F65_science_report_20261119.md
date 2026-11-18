# A01.01.51 — F65: Özgün yedi EOS'un doğrudan LALSuite düşük-basınç türev analizi

**19 Kasım 2026 · Yeni kaynak-fizik deneyi · F58–F64 tekrar edilmedi**

## Ne çözüldü?

JESTER'den alınmış **yedi değiştirilmemiş (F42 olmayan) nükleer EOS** dosyasının her biri, SHA-256 ve özgün kaynak commit'i ile kilitlendi. `lalsuite==7.26.4` içinde yedi EOS'un her biri için, düşük basınçlı özgün #254 düğümünün çevresinde **1.201 yeni P noktasında** doğrudan LALSim `EnergyDensityOfPressureGeometerized(P)` ve `EnergyDensityDerivOfPressureGeometerized(P)` çağrıları yapıldı (**8.407 basınç noktası, her birinde iki C-kütüphane fonksiyonu**). Kaynakta mevcut beş basınç düğümü (#252–256) ise her EOS için doğrudan LAL değerleriyle ayrıca çapraz kontrol edildi (35/35 kaynak-düğüm eşleşmesi; E için maksimum göreli fark tam 0).

**Kaynak özgün EOS'ları hiçbir şekilde değiştirilmedi; 12,9 GB NICER foton arşivi tekrar indirilmedi veya değerlendirilmedi.**

| Özgün EOS | Yeni 1.201 LAL basınç örneğinde negatif c_s² noktaları | Kaynak #254 negatif c_s² |
| --- | ---: | --- |
| APR4_EPP | 0 | Hayır |
| ENG | 205 | Evet |
| MPA1 | 205 | Evet |
| MS1 | 205 | Evet |
| MS1B | 205 | Evet |
| WFF1 | 205 | Evet |
| WFF2 | 205 | Evet |

Altı özgün EOS (**ENG, MPA1, MS1, MS1B, WFF1, WFF2**) doğrudan kaynak fonksiyonunda **205 ardışık** örnek noktasında negatif \(c_s^2/c^2=1/(d\varepsilon/dP)\) gösterdi; **APR4_EPP için bu belirli basınç penceresinde sıfır** negatif nokta var. Her altı modelde aynı örnek penceresi bulundu:

- Basınç örnek aralığı: **5.057294464870e-16 – 5.215732229519e-16 m⁻²** (geometrize basınç).
- Örneklenen negatif bölgenin uçları arasındaki genişlik: **1.584377646488e-17 m⁻²** (orta basıncın yaklaşık **3.085%**'ü). Bu, *örneklenmiş* aralıktır; kesin matematiksel sürekli aralık sınırı değildir.
- Altı EOS'un bu taramada **enerji yoğunluğu eğrilerinin en yüksek bağıl farklılığı 1.2436e-08**. Bu güçlü ortak düşük-P yapısı kanıtıdır, fakat kabuk katmanının hangi uygulama satırından kaynaklandığını kesin olarak belirlemez.
- Bağımsız LAL analitik türevlerine ek olarak doğrudan E(P) enerji tablosunda **206 negatif sonlu-fark eğimi** kaydedildi; böylece salt sembolik yanlış işaret veya tek kaydedilmiş cs² hücresi olmadığı doğrulandı.

**Yeni bilimsel sonuç:** MPA1'de önceden bilinen negatif-c_s² sorunu tek bir JESTER örnekleme düğümünden doğan istatistiksel bir görünüm değil; özgün LAL enerji ve türev fonksiyonlarıyla bağımsız yüksek çözünürlüklü taramada negatif türevli bir düşük basınç bölgesi olarak yeniden üretildi. Altı farklı EOS'da neredeyse aynı yapı olması, ortak kabuk/interpolasyon bileşeninin incelenmesini öncelikli hâle getiriyor. Ancak **gerçek termodinamik faz geçişi mi, tabular interpolasyon mu, özel kaynak verisindeki kusur mu?** sorusu henüz nedensel olarak çözülmedi. Model 'düzeltildi' veya 'fiziksel olarak imkânsız altı EOS' denmedi.

## Sayısal ve bütünlük kanıtı

- Tam çalışma ve 15/15 fail-closed kod testi: [F65 GitHub Actions gerçek LALSuite koşusu](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44405084469).
- Ham JSON SHA-256: `6e35cd5ea33d3f3e9e3d0fb7cee585f809638e4b8507804bd7c0789148cd6e74` (dosya 781016 bayt).
- CI ZIP SHA-256: `5e11ff7bde936ddb6deaff5055f7de708ec861516471a5f3f2f05adefb1dd4ba`, ZIP CRC PASS; içeride hash makbuzu `F65_source_SHA256_manifest_20261119.json`.
- LALSuite **7.26.4**, JESTER source SHA commit `e6768650ce992abfd1153a6833857572fe5cd230`; 7/7 özgün NPZ hash'i ayrı manifestte.
- [F65 GitHub PR #627](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/627) — kayıt ve CI.

## Bilimsel kabul sınırı ve sıradaki iş

Bu **sonlu basınç taraması**, bütün yıldızın sürekli nedensellik sertifikası, faz geçişi tanısı, n(P)/H(P) birinci-yasa bütünleştirmesi, baryon normu, gerçek X-PSI foton+nuisance olabilirliği veya **özgün yedi-EOS Bayes çıkarımı değildir**. F63/F64 RNS geometrik hesapları ile bu düşük-P model kusurunun birlikte nasıl etkilediği henüz çözülmedi. Negatif türevi basitçe kırpıp özgün MPA1 etiketiyle kullanmak yasaktır.

Bir sonraki **yeni** kabul deneyi: LAL EOS kaynak/tanım kümesindeki bu basınç segmentinin gerçek kabuk eşleştirme tablosuyla ilişkisini test etmek; tanımlı fiziksel kabuk geçişli ayrı bir *yeni* EOS hipotezini ilk-yasaya uygun n(P), H(P) ve nedensellikle karşılaştırmak. Ancak bundan sonra özgün X-PSI likelihood ve çift sayım olmadan tüm kütle önseliyle karşılaştırma.

**Kanonik depo:** `A01.01.51/PSR_J0740+6620/F65*` ve `F65_source/`; veri, rapor, kaynak, test, CI ZIP, özgün hash makbuzu. Eski F58–F64 raporları değiştirilmedi.
