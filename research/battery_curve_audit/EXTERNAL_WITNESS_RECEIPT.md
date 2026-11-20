# CANO Batarya V7 — dış tanıklık anahtarına bağlı çevrimdışı kanıt makbuzu

**Amaç:** V6 kör inceleme sonuçlarını; operatörün kendi beyanı dışında, daha önceden güvenilir bir kanaldan kurulmuş, kurum/dış tanık tarafından ayrı korunan 32 baytlık *simetrik* anahtarla ilişkilendirmek. **Yapılabilen şey kayıt bütünlüğüdür; gerçek kurum yetkisi, hukukî imza, iki gerçek insanın bağımsızlığı, kayıt zamanının doğrulanması ve fiziksel deney kabulü bu yazılımla kanıtlanmaz.** Çıktının `field_acceptance` alanı daima `NOT_ESTABLISHED` kalır.

## Kanıt zinciri

1. Laboratuvar sahibi özgün CSV ölçümlerini, kaynak manifestini, ayrı numune kimliklerini ve izin kaydını yetkili ortamda tutar. Önce V6 `blind_field_review.py screen / prepare / finalize` akışını tamamlar; V6'nın **ayrıca saklanan özel operatör anahtarı** olmadan bu aşama geçilemez.
2. `external_witness_receipt.py prepare`, V6 **finalize** işlemini geçici yeni dosyaya yeniden çalıştırır. Böylece ham kaynak CSV'leri, HMAC'li gizli örneklem, model bayrakları, iki tamamlanmış teknisyen formu, SHA makbuzu ve herkese açık olmayan özet birlikte yeniden kontrol edilir. Önceden tamamlanan özetin baytları aynı değilse işlem durur. Özel bir **challenge.json** kaydı oluşturulur: dokuz kanıt dosyasının SHA-256 değeri, rastgele istek değeri (`nonce`) ve salt/nonce'a bağlı teknisyen takma-adı özeti. **İstek özeldir; cihaz kimlikleri başka düşük entropili metinler içeriyorsa hash'ler de ilişkilendirilebilir.** İzin referansı ve gerçek kimlikler genel sonuçta yayımlanmaz.
3. Ayrı tanık, kendi kurumu/cihazı/yetki belgesi konusunda **insan olarak bağımsız inceleme** yapar. Kurum anahtarı bu işlemden **önce**, başka güvenli kanaldan yetkili kişi tarafından oluşturulmuş/teslim edilmiş olmalıdır. `endorse` bu anahtarla özel isteğe HMAC-SHA256 üretir. `endorse` komutu **tek başına** kimlik veya yetki doğrulamaz; operatörün kendine anahtar üretip sahte onay alması yazılımla engellenemez.
4. Ayrı doğrulayıcı, dış kanaldan önceden kendisine bildirilen tanık anahtarının **SHA-256 parmak izini** bağımsız olarak tutmalıdır; parmak izini istem/yanıt dosyasından kopyalamak güven ilişkisi kurmaz. `verify`, önce bağımsız parmak izi eşleşmesini ve HMAC'i kontrol eder. Sonra **bütün mevcut kaynakları tekrar okuyup** gerçek V6 incelemesini aynı değiştirilemez ölçüm/kayıt şartlarında tekrar yürütür. Hangi CSV veya formun bir baytı değişse, imza değiştirilse veya farklı kök kanıt bağlansa işlem durur. Sonuç yalnız `WITNESS_KEYED_INTEGRITY_MATCH_ONLY` şeklindedir; **saha kabulü değil**.

## İşlem komutları

Python 3.12+, yalnız standart kütüphane. Aşağıdaki örnekler yerel laboratuvar ortamında tek PowerShell komutuna uyarlanmalıdır. `--root` ham ölçümlerin güvenilir klasörüdür. Her komut için aynı V6 kaynak dosyalarını ve `--reviewer-a-id`/`--reviewer-b-id` metinlerini kullanın:

```text
--manifest C:\Lab\manifest.json
--audit C:\Lab\audit.json
--cells C:\Lab\cells.csv
--pairs C:\Lab\private-pairs.csv
--frame C:\Lab\frame.json
--form-a C:\Lab\tech-A-dolduruldu.csv
--form-b C:\Lab\tech-B-dolduruldu.csv
--seal C:\Lab\operator-only.json
--public-summary C:\Lab\private-safe-aggregate.json
--root C:\Lab
--operator-key D:\OperatorKeys\operator-only.key
--reviewer-a-id TECH_A
--reviewer-b-id TECH_B
```

* Laboratuvar operatörü: `python research/battery_curve_audit/external_witness_receipt.py prepare [yukarıdaki tüm parametreler] --request C:\Lab\private-witness-challenge.json`
* **Ayrı tanık:** `python research/battery_curve_audit/external_witness_receipt.py endorse --request C:\Lab\private-witness-challenge.json --witness-key D:\IndependentWitness\witness-32-byte.secret --endorsement C:\Lab\witness-response.json`
* **Ayrı doğrulayıcı:** `python research/battery_curve_audit/external_witness_receipt.py verify [aynı ilk parametreler] --request C:\Lab\private-witness-challenge.json --endorsement C:\Lab\witness-response.json --witness-key D:\IndependentWitness\witness-32-byte.secret --expected-witness-key-sha256 <önceden ayrı doğrulanmış 64-hex parmak izi> --output C:\Lab\new-witness-aggregate.json`

Windows'ta erişim izinleri için güvenilir ACL yapılandırması gerekir; `chmod 600` yalnız POSIX üzerinde kontrol edilebilir. Anahtar düz metin dosyası **tam olarak 32 rastgele bayt** olmalıdır; metinsel parola, satır sonu, base64 string değildir. Bu uygulama anahtarı üretmez. Kök anahtar şifrelemesi, donanımsal anahtar koruması, kurumsal kimlik doğrulama, güncel/geri alınmış yetki listesi ve yeniden oynatmayı engelleyen bağımsız kayıt sistemi bu protokole **dahil değildir**.

## Fail-closed ölçütleri

- Yanlış/eksik/kapsamı genişletilmiş istek, değişmiş HMAC, farklı tanık anahtarı, yanlış dış pin; kontrol dışı gizli anahtarın operatör anahtarıyla aynı olması; kaynak veya değerlendirme değişikliği → `REVIEW_REQUIRED`, **yeni sonuç dosyası üretilmez**.
- Çıktı güvenli koşulda dahi `site_authorization_independently_verified=false`, `distinct_reviewer_humans_authenticated=false`, `freshness_or_replay_independently_verified=false`, `field_acceptance=NOT_ESTABLISHED` taşır. Gerçek kurumun kimliğini ve yetki zincirini bağımsız olarak incelemeden ürün/site sertifikası vermeyin.
- Yalnız sentetik örneklerle yapılan otomatik testler fiziksel ölçümleri veya bağımsız insan tanıklığını doğrulamaz. BulyK47 / POLITEHNICA Bucharest kaynakları (DOI 10.21227/cm0f-jg66, CC BY 4.0) önceki veri bütünlüğü araştırması içindir; burada gerçek bir müşteri/kurum imzası bulunmaz.
- **Güvenlik sınırı:** HMAC simetriktir, güçlü bir sayısal imza yerine geçmez. Anahtarı ele geçiren kişi tanıklık üretebilir; aynı kişi hem anahtarı sağlıyor hem veriyi hazırlıyorsa bağımsızlık yoktur. Gerçek dış doğrulama için kurumun doğrulanmış imza anahtarı ve harici güven zinciri gerekir.
- **Gizlilik:** Ham müşteri verileri, gerçek personel kimlikleri, HMAC anahtarları, `operator_only.json`, doldurulmuş gerçek reviewer formları ve özel challenge GitHub/Notion/Library/chat/Render/Neon'a yüklenmez. Genel özet sadece türetilmiş durum bilgisi içerir.

## Yerel denetim

`python -m unittest discover -s tests -p 'test_battery_external_witness_receipt.py' -q` — tamamen sahte/sentetik, geçici dizin ve test için ayrılmış sahte tanık anahtarı. Diğer mevcut batarya testleri ile birlikte de tekrar çalıştırılmalıdır. Gerçek tanık anahtarı örneklerde/pakette bulunmaz.
