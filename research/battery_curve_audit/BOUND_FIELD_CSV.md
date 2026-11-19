# CANO — özgün batarya CSV'si ↔ laboratuvar teknisyen CSV'si, tek doğrulama komutu

**Durum:** yalnız çevrimdışı ve ücretsiz Python 3.12+ yazılım pilotu. Müşteri sahası, teknisyen bağımsızlığı, cihaz kalibrasyonu, akredite analiz veya batarya SOH doğruluğu belgesi **değildir**.

## Hangi riski kapatıyor?

Tek başına `field_pilot_csv_intake.py`, teknisyen/cihaz tablolarının kendi iç tutarlılığını ölçer fakat `frame.json` içindeki SHA-256 makbuzunun gerçekten aynı ölçüm raporuna ait olduğunu doğrulamaz. Ayrı `field_receipt_binding.py` ise gerçek CSV denetimi yapar ama hassas JSON saha defterini elle üretmek gerekir. `field_source_csv_bridge.py` **mevcut iki modülü tekrar yazmadan** tek komutta bağlar. Kaynak raporun **tam bayt SHA-256'sını** karşılaştırır, özgün yerel zaman-gerilim CSV'lerini yeniden hesaplar, önerilen bölmenin hücre kimlikleri ile teknisyen CSV'sini birebir eşleştirir. Aynı cihaz/parti/kampanya veya iki teknisyen uzlaşısı farklı test bölmelerine uzanıyorsa engeller.

## Girdiler ve kullanım

Aynı yetkili laboratuvar bilgisayarında şu özel dosyalar bulunmalı:

- `manifest.json` ve bu manifestte gösterilen **orijinal kaynak CSV'leri** (`CUSTOMER_PIPELINE.md`).
- Değiştirilmemiş `private-source-audit.json`: önce `integrated_customer_gate.py --manifest ... --root ... --report private-source-audit.json` ile üret. Rapordaki bölme *taslak* olabilir; `REVIEW_REQUIRED` ise son kabul **asla** verilmez.
- `cells.csv`, `reviews.csv`, `frame.json`: tam başlıklar ve onay sınırları `FIELD_PILOT_CSV_INTAKE.md` dosyasında. `cells.csv` içindeki bölmeler kaynak raporunun `split.assignments` bölümündekilerle **birebir aynı** olmalı.
- `frame.json` içindeki `audit_receipt_sha256`, **tam audit JSON dosyasının** yerel SHA-256 özetidir. Örneğin: `python -c "import hashlib;print(hashlib.sha256(open('private-source-audit.json','rb').read()).hexdigest())"`.

```sh
python research/battery_curve_audit/field_source_csv_bridge.py \
  --manifest ./lab/manifest.json --root ./lab \
  --audit-report ./lab/private-source-audit.json \
  --cells ./lab/cells.csv --reviews ./lab/reviews.csv --frame ./lab/frame.json \
  --summary ./lab/NEW-redacted-verified-summary.json
```

Windows ZIP paketinde `Run-Field-Verified.cmd` aynı sıradaki **altı tam dosya yolunu** ister: manifest, kaynak denetim raporu, cells.csv, reviews.csv, frame.json, **yeni** summary.json. `--root` kendiliğinden manifest klasörüdür. Varsayılan rapor yalnız agregaları içerir, özel müşteri isimleri/cihaz/teknisyen kimlikleri veya kaynak SHA yer almaz. `--private-ledger` varsa özel saha JSON'u **yalnız kullanıcının yerel korunan klasörüne** yazılır; isteğe bağlıdır, kesinlikle yayımlanmaz. Mevcut çıktı dosyası, özel ham ölçüm veya diğer girdiler **silinmez ve üzerine yazılmaz**; POSIX 0600 oluşturulur, Windows erişim izinlerini laboratuvarın ayarlaması gerekir.

Kararlar: `PILOT_ONLY_NOT_CERTIFIED` yalnızca kaynak + teknisyen tabloları **tutarlı bir tarama** geçirdiği anlamına gelir (exit 0); saha kabulü **asla** değildir. `BLOCK_AUDIT_REVIEW` gerçek kaynakta tekrar kontrol gerektiren kopya/şüpheli eğriyi; `BLOCK_PROVENANCE_LEAKAGE` cihaz/parti/kampanya/teknisyen veri bölmesi sızıntısını; hata/uyuşmazlık exit 2 ile engellenir. Eksik, değiştirilmiş veya sahte kaynak dosyası, rapor, makbuz veya hücre bölmesi için yeni rapor oluşmaz.

## Gerçek deney / iş modeli sınırı

Bu araç, JSON makbuzunun aynı dosyaya aitliğini **kriptografik tutarlılık** olarak doğrular, kaynak yayımlayıcının sayısal imzasını, gerçek saha sahibinin iznini veya iki teknisyenin gerçekten bağımsız karar verdiğini doğrulamaz. Yanlış alarm/kaçırma oranları yalnızca değerlendirilmiş çiftlerin iki-uzlaşı örneklemi içindir. Gerçek izinli, bağımsız cihaz/laboratuvar deneyi ve müşteri ödeme isteği hâlâ ayrıca araştırılmalıdır. Kaynak ölçümler internete, Notion'a, GitHub'a, Render veya Neon'a gönderilmez.

Sentetik test: `python -m unittest discover -s tests -p 'test_battery_bound_field_csv.py' -v`. Paket doğrulama: `python verify_package.py --tests --demo`. Bükreş Politeknik/BulyK47 kaynak veri DOI 10.21227/cm0f-jg66 (CC BY 4.0) ve ayrı David-EIPI SOC kaynak verileri için kendi lisans koşulları geçerlidir; bu araç ikisini aynı fiziksel eksen olarak birleştirmez.
