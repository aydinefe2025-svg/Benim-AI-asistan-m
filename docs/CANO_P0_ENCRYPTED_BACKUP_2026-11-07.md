# CANO — P0 şifreli taşınabilir PostgreSQL yedek ve izole geri yükleme

## Bu araç neden var?
Canlı CANO verisi Neon üzerindeki `assistant_pg` veritabanında bulundu (7 Kasım 2026, yalnız şema ve satır sayıları okundu). Aynı Neon projesindeki anlık görüntü/kurtarma dalı **bağımsız dış yedek değildir**. Kaynağın erişilemez olması durumunda başka bir PostgreSQL örneğine kurtarma için kendi saklama alanında **şifreli, bağımsız taşınabilir kopya** gereklidir. Render'ın farklı, kullanılmayan ücretsiz araştırma veritabanının son tarihi bu konuyla karıştırılmamalıdır.

## Gerçekten uygulanan güvenlik

- Yeni `scripts/cano_encrypted_backup.py`, `pg_dump -Fc` akışını **doğrudan AES-256-GCM** ile şifreler; **düz metin `.dump` dosyası yazmaz**. Anahtarın bulunduğu değişken, pg_dump/pg_restore/psql işlemlerine kesinlikle geçirilmez. Gizli bağlantı URI'si argv veya log çıktısına yazılmaz.
- Her dosya için rastgele 96-bit nonce, kimliği doğrulanmış başlık, GCM etiketi, dosya SHA-256 ve şifreli kopyaya özel receipt. Dosya değişirse veya anahtar yanlışsa doğrulama kapanır.
- Restore **önce tüm şifreli dosyayı doğrular**, ardından yalnızca açıkça belirtilmiş, ayrı, boş, ismi `cano_restore_` ile başlayan veritabanına geri yükler. SQL işlemi tek transaction'dır; `pg_restore` stdin üzerinden beslenir (düz metin yedek dosyası diske yazılmaz). Restore'un tamamlanması gerçek satır bazlı kıyas gerektirir; CI bunu yapar.
- Sızma önlemi: gerçek bağlantı şifreleri, AES anahtarı, özel bellek/ajan verileri, şifreli gerçek yedekler **GitHub'a/Notion'a/sohbete yüklenmez**.

## Eylem / kullanım (yalnız kullanıcı kontrollü bilgisayarda)

1. PostgreSQL istemcileri `pg_dump`, `pg_restore`, `psql` ve `cryptography` kurulu olmalı. Kaynak sürümüne uyumlu pg_dump kullan.
2. Rastgele **32 baytlık** `CANO_BACKUP_KEY_HEX` anahtarını **kendi cihazında** üret; ChatGPT'ye, GitHub'a, Notion'a veya Render günlüklerine koyma. Anahtarın bağımsız ve çevrimdışı bir kopyası olmazsa yedek **geri döndürülemez**.
3. Seçilen kaynak veritabanının `DATABASE_URL` bağlantısını cihazın gizli ortamında tut; bunun CANO'nun doğru ana PostgreSQL verisi olduğundan emin ol.
4. Başka sağlayıcıdaki **özel, kalıcı** hedef klasörde `python -m scripts.cano_encrypted_backup backup <HEDEF_KLASÖR>` çalıştır. Çıkan `.canoenc` ve `.receipt.json` dosyalarını ayrı sakla; anahtarı aynı yere koyma.
5. `python -m scripts.cano_encrypted_backup verify <HEDEF_KLASÖR>/<receipt>.json` ile dosya/etiket ve plaintext hash denetimi yap.
6. **Yalnız ayrı ve boş** `cano_restore_...` veritabanının `CANO_RESTORE_DATABASE_URL` bağlantısıyla `python -m scripts.cano_encrypted_backup restore-isolated <dosya.canoenc> --confirm-empty-isolated-target` çalıştır. Kullanıcı kayıtlarını gizlilik içinde/yerinde kıyasla.

## Bağımsız CI neyi ispatlar?

PostgreSQL 17/18 için dokuz **gerçeğe benzer isimli ancak tamamen sahte tablo**, 18 sahte satır oluşturulur. Gerçek `pg_dump` → AES-GCM → doğrulama → ayrı boş `cano_restore_...` DB'de gerçek `pg_restore` → satır ve owner ayrımı kıyaslanır. Bozuk anahtar, ikinci kez restore, eksik kaynak, silinmeyen geçici plaintext ve symlink senaryoları reddedilir. **Gerçek Neon üretim yedeğinin çıktığı veya dış depoda olduğu iddia edilmez**; gerçek operatör kurulumu/harici hedef ayrı kapıdır.

## Maliyet / koruma

Yalnız açık kaynak araçlar ve GitHub'ın sentetik CI veritabanı kullanılır. Hiçbir ücretli sağlayıcı, gerçek üretim veritabanında yazım/deploy veya güvenlik duvarı değişikliği otomatik başlatılmaz. Gerçek dış yedek oluşturmaya başlamadan bağlantı yetkisi ve hedefin kalıcılığı özel olarak doğrulanmalıdır.
