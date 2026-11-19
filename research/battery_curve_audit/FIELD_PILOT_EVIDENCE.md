# CANO Batarya — çevrimdışı saha ön-kabul kanıt kapısı (19 Kasım 2026)

**Kapsam:** Laboratuvarın onay verdiğini kendisinin beyan ettiği **özel** saha pilotu
metaverilerini ve iki teknisyenin eşleştirme kararlarını *yerelde* değerlendiren bir
araştırma prototipi. Kalibrasyon, akreditasyon, gerçek saha testi ve ticari kabul
**değildir**. Tamamen Python standart kütüphanesiyle çalışır; veriyi sunucuya göndermez.

## İhtiyaç

Önceki [birleşik müşteri CSV denetimi](CUSTOMER_PIPELINE.md), metinsel / sayısal
kopyaları ve 2 mV yakın-kopya adaylarını tarar, fakat **aynı test cihazının**,
**ortak hücre/üretim partisinin** veya **aynı edinim kampanyasının** farklı
train/validation/test bölmelerine ayrılmasını laboratuvar kaydı olmadan bilemez.
Ayrıca laboratuvar uzmanının bir adaya ne karar verdiğini ve hangi adayların hiç
incelenmediğini değerlendiremez. Bu yeni araç CSV ölçümlerini tekrar okumaz;
yalnızca ayrı, açıkça kullanıcı tarafından hazırlanmış özel saha defterini kontrol eder.

## Kullanım

```sh
python research/battery_curve_audit/field_pilot_evidence.py \
  --ledger ./authorized-private-ledger.json \
  --summary ./redacted-field-summary.json
python -m unittest discover -s tests -p 'test_battery_field_pilot_evidence.py' -v
```

Örnek şema (yalnız **sentetik** kimlikler ve değerler):

```json
{
  "schema":"cano.battery.field-pilot.v1",
  "audit_receipt_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "site_authorization":{"permitted":true,"reference":"FICTIONAL-APPROVAL"},
  "cells":[
    {"cell":"A","device":"device-1","batch":"batch-1","campaign":"session-1"},
    {"cell":"B","device":"device-2","batch":"batch-2","campaign":"session-2"},
    {"cell":"C","device":"device-3","batch":"batch-3","campaign":"session-3"}
  ],
  "assignments":[
    {"cell":"A","partition":"train"},
    {"cell":"B","partition":"validation"},
    {"cell":"C","partition":"test"}
  ],
  "screened_pair_count":3,
  "screened_flagged_count":1,
  "reviews":[
    {"a":"A","b":"B","flagged":true,
     "reviewer_a":{"id":"reviewer-1","verdict":"linked"},
     "reviewer_b":{"id":"reviewer-2","verdict":"linked"}}
  ]
}
```

Her hücrenin cihaz/parti/kampanya kimliği zorunludur. Bu ortak etiketler
**muhafazakâr** bir olası bağımlılık bağlantısı kurar: bağlantılı hücreler
farklı bölmelerdeyse `BLOCK_PROVENANCE_LEAKAGE`. İki teknisyenin `linked`
uzlaşısı bölmelerin dışına taşarsa yine engellenir; yalnız görüşleri aynen
sınıflandırılır, bu görüşler fiziksel kopyanın kesin kanıtı değildir.

Bütün bölmeler için hücre eşleştirmesi zorunludur. Tarama çerçevesindeki çift
sayısı ve işaretli çift sayısı, incelenen kayıtlardan **bağımsız** beyan edilir.
İşaretli olmayan çiftlerden örnekleme yapılmazsa yanlış negatif ölçülemez.
İki değerlendiricinin `linked`/`independent` uzlaşısı için:

- `tp`: model işaretledi; her iki teknisyen `linked` dedi.
- `fp`: model işaretledi; ikisi `independent` dedi.
- `fn`: model işaretlemedi; ikisi `linked` dedi.
- `tn`: model işaretlemedi; ikisi `independent` dedi.

Birinin görüşü `unknown` ise **çözümlenmemiş**, ikisi farklıysa **anlaşmazlık**
olur; bunlar paydalara sessizce eklenmez. Paydası sıfır olan metrikler `null`
döner. Birden çok seçilmemiş çift varsa gözlenen oranlar popülasyondaki
başarı/kaçırma oranı **değildir**. Tam çerçeve incelenmiş olsa bile kayıtlar bağımsız
doğrulanmadığı için `field_acceptance=NOT_ESTABLISHED` kalır.

## Gizlilik, sınırlar ve kabul kapısı

`redacted-field-summary.json` yalnız sayılar, durum, denetim koşulları ve açık
belirsizlikler içerir; müşteri/hücre/teknisyen/cihaz/kampanya/parti kimliği,
özel not veya kaynak dosya hash'i **içermez**. Aracı çalıştıran kişi özel
`ledger.json` dosyasının paylaşım ve erişim yetkisinden sorumludur. Çıktı mevcut
bir dosyanın üzerine yazılmaz; POSIX sistemlerde dosya modu `0600` ile oluşturulur.
Windows ACL güvenliği ayrıca sağlanmalıdır. Defter en fazla 1 MiB; 1.000 hücre
ve 10.000 incelenen çift sınırıyla işlenir.

**Kritik:** `site_authorization.permitted=true` bir *kullanıcı beyanıdır*,
imza/yetki doğrulaması değildir. Aynı şekilde denetim makbuzunun 64 karakter
SHA biçiminde olması özgün CSV'leri yeniden hesapladığımız anlamına gelmez.
Bu araç **tek başına hiçbir durumda** güvenilir model, laboratuvar sertifikası,
öngörü doğruluğu veya ücretli müşteri başarısı ilan etmez.

Gerçek pilot kabulü için ayrıca tarafların yazılı/veri yetkisi, ölçüm cihazı
seri geçmişi, numune/batch kaynak zinciri, kör teknisyen etiketleri, negatif
örnekleme protokolü, bağımsız hata tahmini ve maliyet/ödeme onayı gereklidir.

**Açık veri kökeni (önceki deneyler):** [POLITEHNICA Bucharest / BulyK47](https://github.com/BulyK47/battery-datasets), DOI [10.21227/cm0f-jg66](https://doi.org/10.21227/cm0f-jg66), CC BY 4.0. Bu saha protokolü **yeni gerçek müşteri verisi içermez**.
