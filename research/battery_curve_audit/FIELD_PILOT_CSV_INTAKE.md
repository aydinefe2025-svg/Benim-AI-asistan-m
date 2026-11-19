# CANO batarya saha pilotu — laboratuvar CSV giriş kılavuzu

**Durum:** Çevrimdışı, ücretsiz Python 3.12+ pilotu; **gerçek saha kabulü, akredite ölçüm, batarya SOH/SOC teşhisi veya ticari doğrulama değildir.** Bu araç yalnız `field_pilot_evidence.py`'deki mevcut inceleme ve risk kontrolünü kullanır; ikinci bir karar modeli yazmaz.

## Müşteri verisini göndermeden kullan

Tüm dosyalar **yalnızca izinli laboratuvar bilgisayarında** kalmalıdır. Bu uygulama hiç ağ çağrısı yapmaz. Girilen cihaz/parti/teknisyen kodları ve onay referansları özel verilerdir. Şirketin/veri sahibinin izni olmadan bunları Notion, GitHub veya bir dış servise yükleme.

Özel klasörde üç dosya hazırla. Başlıklar ve sütun sıraları birebir aynı olmalıdır. Sayfa programında CSV UTF-8 olarak dışarı aktarılmalı.

**1. `cells.csv`:** hücre başına bir satır; `train`, `validation`, `test` veri bölmesi aynı hücrenin *tüm* ölçümleri için kullanılmalı.

```csv
cell,device,batch,campaign,partition
LAB_A,METER_1,BATCH_7,SESSION_9,train
LAB_B,METER_2,BATCH_8,SESSION_10,validation
LAB_C,METER_3,BATCH_9,SESSION_11,test
```

**2. `reviews.csv`:** teknisyenlerin birbirlerinden **bağımsız ve mümkünse kör** değerlendirmeleri, laboratuvarın kendi sürecinde birleştirilir. Her hücre çifti en fazla bir kez yer alır. Algoritmanın `flagged` kararı küçük harfle `true`/`false` olmalı. Yalnız `linked`, `independent`, `unknown` teknisyen hükümleri kabul edilir.

```csv
a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict
LAB_A,LAB_B,true,TECH_1,unknown,TECH_2,linked
LAB_A,LAB_C,false,TECH_1,independent,TECH_2,independent
```

**3. `frame.json`:** `screened_pair_count` tüm algoritmanın karşılaştırdığı **benzersiz hücre çiftlerinin** sayısı, `screened_flagged_count` bunun içinden uyarı verilenlerdir. Tamamen boş `reviews.csv` yalnız başlık taşıyabilir, fakat bu durumda saha hata oranları hesaplanamaz. `audit_receipt_sha256` önceden üretilmiş *ilgili* denetim raporunun SHA-256 özeti olmalı; program bu beyanı kaynak dosyadan bağımsız doğrulamış kabul etmez. Örnek boş şablonda izin `false`, referans ve SHA ise **bilerek geçersizdir**: yetkili kullanıcı gerçek değerleri girmelidir.

```json
{
  "schema":"cano.battery.field-intake-frame.v1",
  "site_authorization":{"permitted":false,"reference":"REPLACE_WITH_REAL_REFERENCE"},
  "audit_receipt_sha256":"REPLACE_WITH_REAL_64_CHARACTER_SHA256",
  "screened_pair_count":3,
  "screened_flagged_count":1
}
```

**Çalıştırma (repo kökünden):**

```sh
python research/battery_curve_audit/field_pilot_csv_intake.py \
  --cells /private-lab/cells.csv --reviews /private-lab/reviews.csv \
  --frame /private-lab/frame.json --summary /private-lab/NEW-aggregate.json
```

Windows ZIP paketi içinden dört dosya yolunu tırnak içinde ver:

```bat
Run-Field-CSV.cmd "C:\Lab\cells.csv" "C:\Lab\reviews.csv" "C:\Lab\frame.json" "C:\Lab\summary-new.json"
```

Özet yalnızca sayıları, kanıt sınırlarını ve `NOT_ESTABLISHED` saha kabulünü içerir. Ham eğriler, hücre/cihaz/parti/teknisyen kimlikleri, onay referansı ve gizli SHA burada **yer almaz**. İstisnai durumlarda açık `--private-ledger /private-lab/sensitive-new.json` seçimiyle ayrıntılı JSON üretilebilir; **paylaşılmamalıdır**. Dosyalar mevcut bir raporun üzerine yazılmaz; POSIX ortamında yeni dosya 0600 olarak oluşturulur. Windows'ta uygun klasör ACL izinlerini laboratuvar ayarlamalıdır.

`BLOCK_PROVENANCE_LEAKAGE` / `BLOCK_INSUFFICIENT_PROVENANCE_GROUPS` için çıkış 2, yalnız sentetik/yerel pilot ölçümler `PILOT_METRICS_ONLY` için çıkış 0'dır. Çıkış 0 **saha kabulü değildir**. Teknik etiketler doğru veya bağımsızmış gibi kabul edilmez. Hesaplanan yanlış alarm ve kaçırma oranları yalnızca iki teknisyenin uzlaştığı *inceleme örneklemine* aittir, nüfus/popülasyon hata oranı değildir. Personelin kör/bağımsız çalıştığı doğrulanmaz; makbuz hash'i burada orijinal CSV'den kriptografik olarak doğrulanmaz. Pazarlama, kalite sertifikası veya ücretlendirme için bu göstergeler tek başına kullanılamaz.

## Sentetik deneme ve regresyon

Dağıtılan ZIP'teki `demo-data/field_cells.csv`, `field_reviews.csv`, `field_frame.json` tamamen yapaydır. Bunlarla `Run-Field-CSV-Demo.cmd` kontrollü provenance sızıntısı uyarısı verir. Bu dosyaların şablon amaçlı olması gerçek site izni verildiği anlamına gelmez.

```sh
python -m unittest discover -s tests -p 'test_battery_field_csv_intake.py' -v
```

Yayımlayıcıya ait kaynak ölçümleri, bu CSV giriş örneğinde yer almaz. Önceki ayrı gerçek araştırma kayıtları: POLITEHNICA Bucharest (DOI 10.21227/cm0f-jg66; CC BY 4.0), David-EIPI (BSD-2-Clause). Bu yeni modül için **yalnızca sentetik** CSV kabul testleri vardır.
