# CANO Mars | NASA PDS gerçek rover konum verisi denetimi

**Denetim tarihi:** 10 Kasım 2026  
**Araştırma kimliği:** research.mars / evidence.nasa-pds-places-best-tactical / real-coordinate-audit  
**Durum:** Gerçek arşivden alınmış konum/yönelim kayıtları; **Mars arazisi tehlike haritası değildir.**

## 1. Birincil veri, kaynak sürümü ve bütünlük

- **Resmî kaynak:** NASA Planetary Data System (PDS), Mars 2020 **Rover PLACES** paketi, \`data_localizations/best_tactical.csv\`.
- NASA PDS veri adresi: https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/best_tactical.csv
- NASA PDS paket açıklaması: https://pds-geosciences.wustl.edu/missions/mars2020/places.htm
- Dizin: https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_rover_places/data_localizations/
- **Dosyanın PDS dizinindeki değişiklik tarihi:** 30 Temmuz 2026, 17:55; **tam dosya boyutu:** 171.404 bayt. Bu metadata **canlı kaynak dizininden** yeniden okundu. PDS'nin daha eski, önbelleklenmiş dizin görünümü 159.149 bayt gösterdiği için revizyon tarihi ayrıca doğrulandı.
- Depomuzdaki açık veri: \`research/data/mars2020_places_best_tactical_20260730.csv\`.
- Kaynak CSV SHA-256: \`9da19e4f70287fe0d33ba716ff2169c10447c30c7a048583f730e4155226cde9\`.
- Git blob SHA: \`c7829ac70056c342020cffdf0f975eb60a000c74\`.
- 28 başlık alanı; **666 veri satırı**: 88 \`SITE\`, 578 \`ROVER\`; sol/SCLK bilgileri doğrulanan **577 ROVER konumu**, 1 zaman işaretsiz konum hariç.

## 2. Ölçülen gerçek alanlar ve sayısal sonuçlar

| Ölçüm | Kaynak-veri üzerinde hesaplanan değer |
|---|---:|
| Kayıtların zaman kapsamı | sol **13–1896** |
| Farklı sol sayısı | **468** |
| Ardışık zamanlı konum çifti | **576** |
| İki konum arasındaki düz çizgi yatay mesafelerin toplamı | **36,834 km** |
| Bölüm başına yatay düz çizgi medyanı | **29,353 m** |
| En uzun örneklenmiş konumlar arası düz çizgi | **544,273 m** |
| Aynı sol içinde başlayan ve biten ardışık çift | **109** |
| Arasında birden çok sol bulunan çift | **295** |
| En geniş sol farkı | **47 sol** |
| Kaynak \`landing\`–\`northing/easting/elevation\` çerçeve tutarsızlığı, üst sınır | **0,001 m** |
| Kaynak kuaterniyon normunun 1'den azami sapması | **6,24×10⁻¹⁰** |

**Yorum:** 36,834 km, konum örnekleri arasında düz çizgi (chord) uzaklıklarının toplamıdır; **rover odometresi değildir**. Ara hareketler, virajlar, tekerlek kayması ve ölçüm düzeltmeleri bu veriden çıkarılamaz. Sol farkının 47'ye ulaşması nedeniyle bazı ardışık örnekler zaman bakımından seyrektir. Bu özet NASA'nın 11 Ekim 2026 için yayımladığı 45,22 km odometre duyurusuyla aynı şeyi veya aynı dönemi ölçmez; doğrudan doğrulama kıyası yapılamaz.

## 3. Güvenilirlik kapıları

\`research/mars_places_track_audit.py\` yalnızca Python standart kütüphanesini kullanır. Kaynak dosyasını dışarıya çağrı yapmadan okur ve şunları denetler: doğru 28 sütun, eksik/fazla sütun reddi, finiteness (\`NaN/inf\` engeli), \`site/drive\` tekrarları, saat/sol sıralaması, beklenen konum çerçevesi dönüşümleri ve kuaterniyon normu. Geçersiz kayıt hata verdiğinde analiz sonucu başarı diye yazılmaz.

Ayrı \`research_reports/mars/2026-11-10_places_pds_independent_check.json\` dosyası, gerçek 666 satırın tamamı üzerinde bağımsız JavaScript hesaplamasından üretilmiştir. \`tests/test_mars_places_track_audit.py\` Python sonuçlarını bu ikinci hesapla karşılaştırır; kaynak SHA-256'yı ve ölçülen geometriyi kontrol eder.

Tekrar üretim (depo kökünde):

\`\`\`bash
python -m research.mars_places_track_audit
python -m unittest discover -s tests -p test_mars_places_track_audit.py -v
\`\`\`

## 4. Bilimin sınırı — özellikle yanlış keşif iddialarını engellemek için

**Bu deneyin kanıtladığı:** NASA'nın gerçek lokalizasyon tablosunun tutarlılığını ve örneklenmiş konumlar arasındaki mesafeleri hesaplayabiliyoruz; sonuç ve kaynak sürümü doğrulanabilir.

**Bu deneyin kanıtlamadığı:** Mars'taki kum, kayalar, kaya kayması, eğimle ilişkili sürüş tehlikesi, gerçek batarya tüketimi, tekerlek kayması, gerçek bir yeni güzergâhın güvenliği veya Mars'ta yaşam. \`roll\` ve \`pitch\` rover poz ölçümleri olup tek başına yerel arazi eğimi haritası sayılmaz. Yerel sentetik rota planlayıcısı \`research/mars_rover_navigation.py\`, NASA'nın gerçek arazisine kalibre edilmiş değildir.

**Yüksek değerli sonraki deney:** Aynı konum noktalarını gerçek PDS \`data_maps\` DEM/DTM ile **koordinat sistemi ve piksel ölçeği doğrulanmış biçimde** eşlemek; eğim ve arazi maske değerlerini kalibrasyonla çıkarıp yalnızca o zaman gerçek arazi temelli bir deneme raporlamak. Yerelizasyondan kum/taş riski üretmek yasaktır.

CANO Render PostgreSQL 18 veritabanının 2 Aralık 2026 felaket-kurtarma P0 görevi ayrı konudur. Bu araştırma ona ilişkin yedek oluşturulduğunu iddia etmez.
