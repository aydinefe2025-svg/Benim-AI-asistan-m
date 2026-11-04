# 3 Kasım 2026 — devam denetimi

## Doğrulanan güncel durum

- PR #51 artık birleştirildi. Birleştirme commit'i:
  `d0e144e9d62b62337fa1d96a0a1cb1499a2c5f0a`.
  Önceki raporlardaki “PR açık/birleştirilmedi” bilgisi tarihsel kalmıştır.
- Render kaynak dalının son hali
  `d603e57d14aeb2c3860476d810f230695cca2f04` üzerinden ayrı denetim dalı
  açıldı; diğer çalışmalarda eklenen görev/kanıt düzeltmeleri korundu.
- Bu kaynakta Windows/Python 3.15.2 ile **196/196 unittest başarılı**.
  `pip check` başarılı. MuJoCo 3.17.0 serbest düşüş, seri/batch eşdeğerliği,
  temas ve 7 tekrarlı ölçüm kontrolleri yeniden başarılı çalıştı.
- Yerel `data` dizinindeki **10 SQLite veritabanı**, online backup API ile
  `private-backups/verified-20261103` dizinine alındı; farklı
  `private-backups/recovery-20261103` dizinine geri yüklendi. Kaynak, yedek
  ve geri yüklenen verilerin SQL dump özetleri karşılaştırıldı. Bu özel
  dosyalar `.gitignore` kapsamındadır; GitHub'a yalnızca sonuçlar gönderildi.
- Render API mevcut deployment'ı `live` olarak bildiriyor. Gerçekte çalışan
  commit hâlâ `8824269593b2fc0f08bbf446531151b6c21452a7`;
  otomatik dağıtım kapalı. İlk 25 saniyelik sağlık isteği zaman aşımına
  uğradı; ikinci istek HTTP 200 ve tam Streamlit `ok` yanıtı verdi.

Denetim devam ederken kaynak dalına `82cedba` commit'ine kadar ek çalışmalar
birleştirildi. Bunlar da korunarak tekrar test edildi: **200/200 başarılı**.
Bu sonuç ilk 196 testlik kaydın yerini gizlice almaz; iki kaynak anlık görüntüsü
`results.json` içinde ayrı tutulur.

## GitHub Secrets içinden ek erişim denetimi

`provider-connection-diagnostics.yml` iş akışı, repository Secrets içindeki
standart anahtar adlarını yalnızca çalışma ortamına bağlar ve mevcut güvenli
teşhis komutunu çalıştırır. Anahtar değerleri okunup rapora aktarılmaz.
Yalnızca model listesi ve Telegram `getMe` çağrılır; çıkarım, polling veya mesaj
yoktur. Fork PR'larında çalışmaz, yetkisi `contents: read` ile sınırlıdır.
Eksik anahtarlar `not_configured` ve başarısız teşhis sonucu olarak saklanır;
bağlantı sağlanmış gibi gösterilmez. İlk çalışma tamamlandı:
[run 41596702259](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/41596702259)
**başarısız**; Google, Groq ve Telegram için `not_configured` döndü. Bu işin
ortamına standart secret adları sağlanmadı. Bu sonuç başka isim veya korumalı
GitHub Environment altında hiç anahtar bulunmadığını kanıtlamaz; bu kayıtların
konumu bilinmeden kullanılamaz. Aynı kod ağacındaki Core tests ve Public
research checks ise GitHub'da başarılıdır. Teşhis başarısızlığı saklanmadı.

## Önceki engel sınıflandırmasının düzeltilmesi

Özgün talep **robotik veri denetleyicilerinin entegrasyonu** idi. Fiziksel robot
donanımı bağlamak zorunlu bir kabul koşulu değildi. Veri denetleyicileri grid
testleriyle ve MuJoCo fizik kontrolleriyle doğrulandı. Bu nedenle cihaz adresi
verilmemesi özgün görevin engeli olarak sınıflandırılmıyor; fiziksel donanımın
doğrulandığı da iddia edilmiyor.

## Gerçek erişim/veri engelleri

1. **Google ve Telegram:** erişilebilir Kody credential metadata sorgularında
   google/telegram kayıtları bulunmadı. Proje ve bilinen önceki proje kopyasında
   `.env` veya `.streamlit/secrets.toml` yok. Yerel teşhis bu sağlayıcılar için
   `not_configured` ve exit 1 döndürüyor. Gerçek anahtarlar olmadan kimlik
   doğrulaması tamamlanamaz. Yerel Groq anahtarı da yoktur; önceki canlı
   Groq doğrulaması bundan ayrı bir ortamda yapılmıştır.
2. **Canlı Render verisi:** alınan 10 dosyalık yedek **yerel kopyaya aittir**,
   Render sunucusunun verisini içermez. Servis free planında ve mevcut
   bağlantı araçları sunucunun özel SQLite dosyalarını indirmek için SSH/shell
   veya dosya erişimi sağlamıyor. Canlı verinin güvenli yedeği doğrulanmadan
   yeniden dağıtım yapılmadı. Kullanıcının “mevcut verileri silme” kuralı
   geçerlidir; yalnızca yerel yedek alındı diye bulut verisi korunmuş sayılmaz.

Neon organizasyonu free planda ancak proje listesi boştur. Yeni bir boş
veritabanı oluşturmak, mevcut Render verisini kendiliğinden kurtarmaz; bu
yüzden kullanılmayan bir kaynak oluşturulmadı. PostgreSQL/persistent-storage
üzerindeki mevcut ayrı çalışmalar incelendi, otomatik birleştirilmedi.

## Sonraki adımı mümkün kılan bilgiler

- Google/Telegram için mevcut gizli anahtarların **güvenli kayıt konumu**
  (değerlerini sohbete veya GitHub'a göndermeyin), ya da bu opsiyonel
  sağlayıcıların kullanılmayacağına ilişkin tercih.
- Mevcut Render verisine ait indirilebilir yedek veya o veriye erişebilen
  yönetim/kalıcı depo kaydı. Bu sağlanınca yedek bütünlüğü ve geri yükleme
  testi geçmeden canlı dağıtım tetiklenmemelidir.

Ücretli işlem, yeni hesap, canlı yeniden dağıtım, veri silme veya nötron yıldızı
araştırma değişikliği yapılmadı. Ayrıntılı makine sonuçları: [results.json](results.json).
