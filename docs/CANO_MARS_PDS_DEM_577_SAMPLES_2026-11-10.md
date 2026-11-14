# CANO — Gerçek NASA Mars Orbital DEM ve 577 Perseverance Konumu

**Tarih:** 10 Kasım 2026. **Durum:** Gerçek PDS veri analizi; uçuş güvenliği veya yaşam keşfi değildir.

## Birincil kaynak ve teknik doğrulama

NASA PDS Mars 2020 Rover PLACES Release 16:
- Rover lokalizasyon CSV: https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/best_tactical.csv
- Orbital DEM ikilisi: https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_maps/m20_orbital_dem.img
- Orbital DEM PDS XML etiketi: https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_maps/m20_orbital_dem.xml
- Resmî paket açıklaması: https://pds-geosciences.wustl.edu/missions/mars2020/places.htm

Sabitlenen XML SHA-256: 7a736fabc434f4c6b4da17e0d943858809d10051570cc06570cb47f3c192e111

Sabitlenen konum CSV SHA-256: 9da19e4f70287fe0d33ba716ff2169c10447c30c7a048583f730e4155226cde9

**P0 kaynak tutarsızlığı çözüldü:** Eski PDS dizin önbelleği orbital DEM'i 297.047.040 bayt gösteriyordu. Güncel resmî XML 5.480 satır × 14.800 sütun, 32 bit big-endian IEEE float, byte başlangıç ofseti 118.400 veriyor. Doğru hesap 118400 + 5480×14800×4 = **324.534.400 bayt**. Doğrudan HTTP 206 Content-Range başlığıyla bu gerçek boyut doğrulandı. **Tam ikili dosyanın kendisi indirilmedi veya bütünüyle SHA-256 ile doğrulanmadı.**

PDS tablosundaki doğrudan dem_pixel_line / dem_pixel_sample indekslerini yuvarlayarak her pozisyon için 3×3 piksel okuduk. Projeksiyon kaynağı XML'deki 1097070 m maksimum northing ve 4340890 m minimum easting değerleriyle tutarlı; çözünürlük 1 m/piksel. Her 3×3 pencere için 3 adet 12 baytlık satır aralığı, HTTP 206 ile, aralık ve toplam boyut denetlenerek okundu.

## Tüm 577 geçerli pozisyonda gerçek ölçümler

| Ölçüt | Değer |
|---|---:|
| Geçerli rover konumları | 577 |
| Gerçek 3×3 DEM piksel örnekleri | 5.193 |
| Tekil 3-piksel satır byte aralığı | 1.681 |
| HTTP aralık istek grubu | 61 |
| DEM–rover yükseklik ortalama mutlak farkı | 0,092969 m |
| DEM–rover yükseklik farkı medyanı | 0,040477 m |
| Farkın %95 yüzdeliği | 0,236824 m |
| En büyük yükseklik farkı | 3,993746 m |
| Farkı 1 m üzerindeki konum | 4 |
| Yerel DEM 3×3 gradyan açısı medyanı* | 6,968824° |
| Gradyan açısı %90 / %95 yüzdeliği* | 15,418974° / 17,249537° |
| En büyük gradyan açısı* | 27,413025° |
| Gradyan açısı 15° üzerindeki örnek* | 65 |

*DEM XML'deki piksel birimi **DN**. Yerel gradyan açılarının derece cinsinden yorumu **1 DN = 1 dikey metre varsayımına bağlıdır**. Sayısal DEM değerleri PDS rover yükseklikleriyle çoğunlukla uyumludur fakat dikey datum/birim bağımsız kalibre edilmemiştir. 3×3 görüntü gradyanı kayma, kum/taş tehlikesi, araç gövdesi güvenliği, tekerlek izi veya enerji tüketimi değildir.

## Önemli gerçek aykırı değerler

Dört yüksek farkın **tamamı site 63** içinde görüldü. Sol 1347, 1348, 1349, 1351 sırasında DEM merkezi PDS rover yüksekliğinden sırasıyla yaklaşık 2,316 m, 3,474 m, 3,537 m ve 3,994 m daha aşağıda. İlgili PDS yüksekliği bu dört konumun 3×3 DEM değer aralığının da dışında. Bu nedenle tek başına en yakın piksele yuvarlama açıklaması yeterli değildir.

Bu bir **incelenmesi gereken veri-ürünü uyumsuzluğu** olabilir; NASA'nın hatalı ölçüm yaptığına veya fiziksel anomali bulunduğuna dair kanıt değildir. Dikey datum, orbital DEM'e karşı lokalizasyon referansı ve kaynak ürün revizyonları ayrı doğrulanmalı.

## Tekrar üretim ve bozulma testleri

Ana repo içindeki dosyalar:
- research/data/mars2020_places_best_tactical_20260730.csv
- research/data/mars2020_orbital_dem_label_20260729.xml
- research/data/mars2020_dem_3x3_rover_samples_20260729.json
- research/mars_dem_alignment.py
- research_reports/mars/2026-11-10_dem_independent_metrics.json
- tests/test_mars_dem_alignment.py

Komutlar: python -m research.mars_dem_alignment ve python -m unittest discover -s tests -p test_mars_dem_alignment.py -v

Denetleyici kaynak CSV ve DEM XML özetlerini, 577 pozisyon indekslerini, 3×3 ölçüm matrislerini, JSON normalizasyonuna uygun SHA-256 kontrolünü, istatistikleri ve bağımsız JS hesap raporunu doğrular. 19 test; kaynak, piksel, konum, özet veya bilimsel kapsamın bozulmasını reddeder. İlk CI çalışması JSON sayı gösteriminin saklanan dosyaya göre normalize edilmesi gerektiğini buldu; acquisition öncesi ve saklanan kanonik SHA-256 farklı olduğu için bu durum ayrıca kaydedildi.

**Açık bilimsel eşik:** DEM DN birimini ve site-63 farkını kalibre etmek, gerçek rota güvenliği için arazinin tamamında georeferanslı harita ve rover sensörleri ile doğrulama yapmak. Hiçbir fiziksel rover kontrolü yapılmadı. Mars'ta yaşam tespit edilmedi.

**Ayrı P0:** CANO Render PG18'in şifreli bağımsız dış yedeği hâlâ tamamlanmış değildir; bu Mars çalışması veri kurtarma görevinin yerine geçmez.
