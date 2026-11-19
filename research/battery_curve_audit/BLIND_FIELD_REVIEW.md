# CANO Batarya — kör ve kaynakla eşlenmiş laboratuvar çift inceleme pilotu

**Durum: deney tasarımı ve çevrimdışı yazılım doğrulaması; gerçek saha kalibrasyonu, batarya sağlığı (SOH) tahmini, akredite test veya ticari sertifika DEĞİLDİR.** Python 3.12+ standart kütüphanesi yeterli; müşteri dosyaları ağ üzerinden aktarılmaz. Kullanıcının açık veri erişim izni gereklidir.

## Neden gerekli?

Eski `field_pilot_csv_intake.py` biçimindeki `reviews.csv`, bir teknisyenin hükmüyle birlikte algoritmanın `flagged` kararını da aynı satırda taşıyordu. Teknistenin bunu görmesi kör değerlendirmeyi bozabilir ve ölçülen doğruluk algısını saptırabilir. Yeni `blind_field_review.py` **üç ayrı işlem** sunar; mevcut CANO kaynak denetimi, `field_pilot_evidence.py` ve `field_source_csv_bridge.py` kurallarını aynen kullanır.

1. **`screen` (yalnız operatör):** Özgün ölçümleri, tam birim kontrolünü ve raporun byte-özgünlüğünü `integrated_customer_gate.verify_report` üzerinden *yeniden hesaplar*. Tam Decimal kopya/near/time-origin/2–5 mV offset **inceleme adayı** bilgilerini bütün karşılaştırılabilir hücre çiftleri için **özel** `pairs.csv` dosyasına dönüştürür. Kısa/düz ölçümlerde veya eşleşmeyen ölçüm modlarında yanlış biçimde “temiz” çift üretmek yerine durur. Sayı ve makbuz içeren `frame.json` taslağını otomatik üretir, **`site_authorization.permitted=false`** bırakır. Kurum, gerçek yetkili onayını ayrıca vermelidir; bunu yazılım varsaymaz.
2. **`prepare` (yalnız operatör):** `pairs.csv` ve `frame.json` ile karşılaştırmalı *şüpheli/işaretsiz* gruplardan en fazla `--per-stratum` kadar çifti, işletim sistemi güvenli rastgeleliğinden üretilen anahtarla seçer. Ayrı sıralanmış iki `reviewer` CSV formu yalnız **pair_id, hücre A, hücre B, boş verdict** alanlarını içerir; **algoritma bayrağı yoktur**. `operator_only.json` özel tutulur; hem tüm girdi hashlerini hem de seçilen çiftlerin bayraklarını taşır. **V2 operatör kaydı HMAC-SHA256 ile doğrulanır; rastgele 32 baytlık anahtar ayrı `--operator-key` dosyasında tutulur.** Operatör dosyasını ve kesinlikle anahtarı teknisyenlere yollamayın.
3. **`finalize` (yalnız operatör):** İki formu personel birbirinden ayrı `linked`, `independent` veya `unknown` etiketleriyle doldurduktan sonra, seçilen çiftleri gizli operatör kaydıyla bağlar. Operatörün bir bayrağı değiştirmiş olması dahil, **orijinal çift kararları ölçüm kaynaklarından yeniden üretilerek** karşılaştırılır. Ayrı saklanan 32 bayt anahtarla HMAC bütünlüğü ve gizli örnekleme seçim sırası yeniden hesaplanır; seçilmemiş çiftin formsal yolla sonuca eklenmesi reddedilir. Eski V1 imzasız kayıtlar otomatik kabul edilmez, yeni prospektif örnekleme gerekir. Ardından eski `field_source_csv_bridge` kaynağı, tam SHA-256 rapor makbuzunu, hücre train/validation/test atamalarını, cihaz/batch/kampanya bağlantılarını ve teknisyen uzlaşısını tekrar doğrular. Varsayılan çıktı sadece kimliksiz agregadır. Kaynakta çözülmemiş aday varsa çıktı `BLOCK_AUDIT_REVIEW` olur; gerçek saha onayı **her zaman** `NOT_ESTABLISHED` kalır.

## Pratik komutlar

Her komut yerel çalışma klasöründe yürütülür. Dosyaları kaydettiğiniz klasörün Windows ACL erişim izinlerini laboratuvar yöneticisi sınırlandırmalıdır. Gerçek müşteri dosyalarını GitHub/Notion/chat/Render/Neon’a yüklemeyin.

Önce özgün CSV manifestiyle özel denetim raporu üretin:

```powershell
py -3 research/battery_curve_audit/integrated_customer_gate.py --manifest C:\Lab\manifest.json --root C:\Lab --report C:\Lab\private-audit.json
```

Sıralanan kayıtların hangi `train/validation/test` bölümünde olduklarını `private-audit.json` içindeki mevcut kaynak bölümlemesinden birebir alın. `cells.csv` biçimi `FIELD_PILOT_CSV_INTAKE.md` dosyasındaki `cell,device,batch,campaign,partition` şeklindedir.

```powershell
py -3 research/battery_curve_audit/blind_field_review.py screen --manifest C:\Lab\manifest.json --root C:\Lab --audit-report C:\Lab\private-audit.json --cells C:\Lab\cells.csv --pairs-out C:\Lab\private-pairs.csv --frame-out C:\Lab\frame.json
```

`frame.json` içerisinde yalnız kurumun kendi açık yetkisiyle `site_authorization.permitted` alanını `true`, `reference` alanını da doğru kurum içi referansa çevirin. Sahte izin veya gerçek müşteriyi taklit eden sentetik değerler kullanmayın.

```powershell
py -3 research/battery_curve_audit/blind_field_review.py prepare --cells C:\Lab\cells.csv --pairs C:\Lab\private-pairs.csv --frame C:\Lab\frame.json --audit-report C:\Lab\private-audit.json --reviewer-a-form C:\Lab\reviewer-A-blank.csv --reviewer-b-form C:\Lab\reviewer-B-blank.csv --operator-seal C:\Lab\operator-only.json --operator-key C:\GuvenliKasa\operator-anahtar.bin --per-stratum 25
```

Yalnızca boş A/B formlarını ayrı teknisyenlere sağlayın. Personelin önceki tahminler, ham puanlar veya ortak konuşmalar üzerinden etkilenmesini yazılım engelleyemez; bu organizasyonel kontrollere laboratuvar karar vermelidir. İki teknisyen tüm seçili satırları tamamlayınca:

```powershell
py -3 research/battery_curve_audit/blind_field_review.py finalize --manifest C:\Lab\manifest.json --root C:\Lab --audit-report C:\Lab\private-audit.json --cells C:\Lab\cells.csv --pairs C:\Lab\private-pairs.csv --frame C:\Lab\frame.json --reviewer-a-form C:\Lab\reviewer-A-filled.csv --reviewer-b-form C:\Lab\reviewer-B-filled.csv --operator-seal C:\Lab\operator-only.json --operator-key C:\GuvenliKasa\operator-anahtar.bin --summary C:\Lab\new-redacted-summary.json --reviewer-a-id TECH_A --reviewer-b-id TECH_B
```

**Anahtar saklama uyarısı:** `C:\GuvenliKasa` önceden oluşturulmuş ve yalnız yetkili operatöre erişim veren gerçek, yerel bir klasör olmalıdır. Varsa mevcut anahtarın üzerine yazılmaz. `--operator-key` verilmezse `operator-only.json.key` operatör dosyasının yanında oluşturulur; güvenli saha kullanımında anahtarı **ayrı erişim alanında** tutmak için iki komutta da açık `--operator-key` verin. Anahtarı ZIP'e, Notion'a, GitHub'a, sohbet ekranına veya teknisyen formlarına asla yüklemeyin. Anahtar kaybedilirse eski seçimin bütünlüğü doğrulanamaz, kayıt kabul edilmez. Anahtarı ele geçiren veya hazırlık sırasında farklı anahtarları seçip deneyen operatörün örneklemeyi manipüle edebilme riskini yazılım tek başına ortadan kaldıramaz; ön-kayıtlı örnekleme planı, ayrı gözetmen ve dış anahtar emanet denetimi gerekir. **Bu, HMAC doğrulaması ve deterministik seçimdir; insan imzası, bağımsız kimlik doğrulaması, gerçek körleme kanıtı veya saha sertifikası değildir.**

**Geçiş:** `cano.battery.blind-review-operator-seal.v1` imzasız eski form ve mühürler V2 finalize'a dönüştürülerek yetkilendirilmez. Kanıt zinciri için sıfırdan `prepare` yapılır, iki yeni form tekrar bağımsız doldurulur; eski kayıtlar tarihsel arşiv olarak korunur.

Bu örnekler çok satırlıdır; gerçek PowerShell'de tek fiziksel satır veya uygun satır devam karakteri kullanılır. `operator-only.json`, `private-pairs.csv`, ham denetim raporu, teknisyen formları, cihaz/parti kayıtları **gizli** tutulmalıdır. Raporun mevcut bir dosyanın üzerine yazılmasına izin verilmez; yeni isim verin. Windows'ta dosya ACL'si ayrı ayarlanmalıdır. `--private-ledger` yalnız açık ihtiyaç ve yetkili erişim varsa kullanılır.

## Kabul ve bilimsel sınırlar

- Her iki teknisyenin aynı `pair_id` ve hücre çiftine verdiği hüküm birleştirilir; boş/uyumsuz/tekrarlı satır ve değiştirilmiş prediksiyon reddedilir. İki farklı personel takma adı kullanılması gerçek kör veya bağımsız insan değerlendirmesini **kanıtlamaz**.
- `screen` yalnız algoritmanın **inceleme adayı** tahminini verir; şüpheli = gerçek kopya ve şüpheli olmayan = gerçek bağımsız örnek değildir. 2–5 mV sabit offset için V3 belirsizliği ve farklı cihaz kökeni çözülmez.
- İki aşamalı, işaretlenmiş/işaretlenmemiş **tabakalı örnekleme** ile bulunan TP/FP/FN/TN oranları *yalnızca seçilen çiftler* üzerindedir. Aynı hücre birden fazla çifte girdiğinden örnekler birbirinden bağımsız değildir. **Popülasyon FPR/FNR, ekonomik etki, SOH başarı oranı veya güven aralığı bu sayılardan çıkarılamaz.** Bir grupta hiç gözlem yoksa oran `null` kalabilir.
- Yeni rapor, `field_acceptance=NOT_ESTABLISHED` taşır. Tam bağımsız saha kabulü için iki farklı cihaz/tesis, dış doğrulanmış kaynak kökeni, ölçüm kalibrasyonu, bağımsız kör etiketlerin denetimi ve ileriye dönük yazılı pilot protokol gerekir.
- Kaynak taraması 10.000 hücre çifti bütçesini aşarsa veya karşılaştırılamayan mod/kısa-düz ölçüm varsa negatif sınıfı uydurmak yerine durur. Büyük örnekleme/cihaz kümelemesi için ayrı deney tasarımı gerekir.
- `operator_only.json` dijital imza değildir; yerel operatör dosyaları değiştirebilir. Bağımsız onay için saha sorumlusunun ayrı mühür ve salt-okunur kayıt sistemi gerekir. Herhangi bir satış/akreditasyon iddiası yasaktır.

### Yazılım testleri

```shell
python -m unittest discover -s tests -p 'test_battery_blind_field_review.py' -v
```

Testler sentetik kabul/ret örnekleridir; gerçek müşteri veya fiziksel batarya deneyi içermez. Kaynaklar: BulyK47/POLITEHNICA Bucharest DOI 10.21227/cm0f-jg66 (CC BY 4.0); farklı SOC eksenli David-EIPI kaynağı time/voltage taraması sayılmaz.
