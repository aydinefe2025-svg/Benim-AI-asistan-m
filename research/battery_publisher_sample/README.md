# CANO — Gerçek yayımlayıcı ekip kaynaklı tek batarya ölçümü

**Durum:** Bir kaynak yazarının GitHub deposundaki **tek bir özgün ölçüm CSV'sini** immutable Git commit + dosya Git blob kimliğiyle doğrulayan çevrimdışı gözlem raporu. Bu yöntem Figshare'a konmuş 10 GB ana arşivi indirmeyi gerektirmez. Bu, yayımlayıcı **Figshare arşivinin birebir dosyası olduğunun doğrulaması değildir**.

**Kaynaklar:** Stroebl ve diğerleri, *Scientific Data* (2024), https://doi.org/10.1038/s41597-024-03859-z; Figshare https://doi.org/10.6084/m9.figshare.25975315 (makalede veri lisansı CC BY 4.0); kaynak yazarın analitik deposu https://github.com/fst2112/Multi-Stage-Lithium-Ion-Battery-Aging-Dataset-Analysis. Bu depodaki kodun MIT lisansı, tek başına bütün veri kopyalarını yeniden dağıtma izni sayılmaz. Bu projede ham CSV hiçbir şekilde paketlenmez veya yeniden yayımlanmaz.

## Benzersiz yeni kanıt

- Kaynak yazarın commit'i `145ced182329bb7c1ca00b6b541189721226557e`, tek dosya Git blob `296c18a9bf7d90af1cae7e82f5f82c870bb9c77f`, kaynak boyutu **23.079.267 bayt**. Kaynak dosya `Stage_1/TP_z08_01/TP_z08_01_01_ET_T23.csv`.
- Git blob kimliği `SHA1(b'blob '+str(size)+b'\0'+raw)` olarak bütün ham baytlardan **yeniden üretilir**. Böylece GitHub deposunda aynı ad altında yeniden yazılmış CSV hatalı kabul edilir. Ayrıca SHA-256 hesaplanır.
- CSV `ISO-8859-1` okunur (yayıncı ekibin `src/data_import.py` uygulamasındaki kodlama). **`run_time`, `c_vol`, `c_cur`, `step_type`** zorunludur; yazarın kendi kodu `run_time` değerini saat:dakika:saniyeden saniyeye dönüştürür. Denetleyici her kayıtta zaman [s], gerilim [V], akım [A] parse eder, sayısal olmayanları ve negatif zamanı reddeder; aynı adım içindeki en uzun kesintisiz ve artan-zamanlı kesiti sayar.
- Rapor yalnız toplam satır sayısı, zaman gerilemeleri, adım sayısı, en uzun parçanın uzunluğu ve gerilim/akım aralıklarını içerir. **Gözlem satırları, örnek zaman-serileri veya hücre özel kimlikleri rapora konmaz.** 11 sentetik negatif/pozitif test mevcuttur. 23 MB dosyanın indirilmesi yalnız gerçek GitHub Actions koşusunda gerçekleşir.

## Çalıştırma

Kaynak kodunu GitHub Actions içindeki `battery-publisher-onecell.yml` iş akışı ve `python research/battery_publisher_sample/author_onecell_original.py new-report.json` ile doğrulayın. Yeni rapor dosyası var ise hiçbir zaman üzerine yazılmaz. Örnek kaynak orijinal ham CSV olarak indirilemezse job başarı sayılmaz. No-paywall / ücretsiz kaynak kullanılır.

## Sınırlar ve sonraki fiziksel kapı

- Bu çalışma tek bir kaynak-yazar örneğini doğrular. Makalede geçen **279 ayrı hücrenin** ölçüm dosyalarının 279'u buradan doğrulanmış olmaz.
- Önceki Figshare 30.658 baytlık `experiments_meta.csv` doğrulamasında 279 satır, 141 tekil `serial`, 279 tekil `(stage,serial)` tespit edildi. Ancak bu yeni GitHub örnek dosyasının o metaverideki **aynı fiziksel hücreye** karşılık geldiği bağımsız olarak doğrulanmadı; araştırmacının dosya yolundaki hücre etiketi tek başına güvenilir bir fiziksel kimlik zinciri değildir.
- Bu dosyada tek hücre ölçümü bulunduğundan **birbirinden bağımsız gerçek hücreler için** karışıklık oranı, gerçek kopya tespiti, model doğruluğu veya alan kabulü ölçülemez.
- Ham dosyanın yazardan geldiğini Git blob doğrular; bunu bir başka yayımlayıcıdan veya bağımsız kalibrasyon kurumundan gelen ölçüm kanıtı olarak sunmuyoruz.
- Geçmiş ham zaman ekseninde geri sıçrama tespit edilirse monotonic parçalar dışındaki kesimler için zaman-gerilim karşılaştırması yapılmış sayılamaz. Bir tek örnek bütün veri kümesini temsil etmez.
