# CANO PostgreSQL acil yedekleme kontrolü (4 Kasım 2026)

**Amaç:** Render ücretsiz PostgreSQL'in 30 günlük süre sınırından önce kişisel, bağımsız, şifre açığa çıkarmayan bir yedek almak. Bu belgedeki komutlar **canlı Render sisteminde çalıştırılmadı**. Ancak GitHub Actions'ta PostgreSQL 16 üzerinde gerçek `pg_dump` → `pg_restore` → satır karşılaştırması geçmiştir; veriler sentetiktir. Bu araç yedekleme/inceleme yapar, hiçbir veritabanına restore veya silme yapmaz.

Resmî politika: https://render.com/docs/free (ücretsiz Postgres 30 günde sona erer, Render üzerinde ücretsiz DB yedeği yok; 14 gün ek ücretli yükseltme fırsatı, sonrasında silme). PostgreSQL araçları: https://www.postgresql.org/docs/current/app-pgdump.html ve https://www.postgresql.org/docs/current/app-pgrestore.html .

## Kullanım

1. **Gizli URL'yi terminal komutuna yazmayın ve GitHub'a koymayın.** Ayrı bir şifre yöneticisinden veya kullanıcının kendi makinesindeki güvenli ortam değişkeninden `DATABASE_URL` ya da `AGENT_TASK_DATABASE_URL` yükleyin. `pg_dump` ve `pg_restore` komutları PATH üzerinde olmalı. Ağ erişimi Render'ın izinli bağlantı kurallarına uymalı; kısıtı kaldırıp güvenlik duvarını gevşetmeyin.
2. **Render Free web hizmetinin geçici diskini kullanmayın.** Yedek hedefi kullanıcının kendi kalıcı diski veya özel, korumalı yedek deposu olmalı. Dosyalar hassas kullanıcı verisi içerebilir; GitHub, sohbet, Notion'a asla yüklemeyin.
3. Her iki bağlı veritabanı URL'sini ayrı ayrı inceleyin: `DATABASE_URL` ve `AGENT_TASK_DATABASE_URL` farklı veritabanlarını gösteriyorsa ikisini de yedekleyin. (Aynıysa yinelenen tam yedek gerekmez.)
4. Bellek veritabanını yedekleyin: `python scripts/cano_pg_backup.py backup /path/to/private/backup`. Görev veritabanı için: `python scripts/cano_pg_backup.py backup /path/to/private/backup --database-env AGENT_TASK_DATABASE_URL`.
5. Receipt üzerinde kontrol edin: `python scripts/cano_pg_backup.py verify /path/to/private/backup/cano-postgres-....receipt.json`. İşlem bitince `*.dump` dosyasının ve receipt'in şifreli, yerel ve bağımsız depoda saklandığını doğrulayın.
6. **İzolasyonlu test veritabanında gerçek restore tatbikatı** ayrıca gereklidir: `pg_restore --exit-on-error --no-owner --no-privileges --dbname=<SEPARATE_EMPTY_TEST_DATABASE> <BACKUP.dump>`; kaynak veritabanına restore yapmayın. Parola içeren bağlantı URI'sini komut satırına koymayın. Önce şema/tablo ve satır sayısı kontrollerini, sonra sahip/yetki doğrulamasını yapın.

## Güvence ve sınırlamalar

- İşlem PostgreSQL URL'sini standart libpq `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/`PGDATABASE` ortam değişkenlerine ayırır; tam bağlantı URI'sini komut argümanına veya konsol çıktısına koymaz. Bilinmeyen URL seçenekleri güvenli biçimde reddedilir. Ortam değişkenleri bazı sistemlerde ayrıcalıklı işlemlerce okunabilir; kullanıcı erişimini kısıtlayın. Windows ACL ve şifreli disk güvenliği bu betik tarafından garanti edilmez.
- Yedek `.dump` dosyası geçici ada yazılır; `pg_restore --list` ile ayrıştırma kontrolü başarılı olursa tam ada taşınır. SHA-256, boyut ve tarih ayrı `.receipt.json` dosyasına kaydedilir. Başarısız `pg_dump` sonrasında tamamlanmış yedek diye göstermeyecektir.
- `pg_restore --list` **restore başarısı kanıtı değildir**; receipt `restored_to_new_database=false` taşır. Yerel 8 sentetik birim testi PASS; GitHub Actions'ın **gerçek geçici PostgreSQL 16 sunucusunda** ayrı test veritabanına restore ve iki sahibin JSONB kayıt karşılaştırması 1/1 PASS. Bu, **canlı Render veritabanının yedeklendiğini veya geri yüklendiğini göstermez**.
- Ücretsiz Render PostgreSQL tarih/süre sınırlaması nedeniyle yedeği geciktirmeyin. 2 Aralık 2026 CANO proje kayıtlarındaki hedef tarihtir; **güncel gerçek son tarih Render panelinden ayrıca doğrulanmalıdır**.

## Gerçek izole PostgreSQL entegrasyon kanıtı

- CI (4 Kasım 2026): [PostgreSQL restore rehearsal — PASS](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/41837886493), [Core Windows/Ubuntu — PASS](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/41837886435), [Public research — PASS](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/41837886400), [Evidence gate — PASS](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/41837886348). Son kod, `fix/cano-pg-backup-real-restore-20261104` dalında ayrıca doğrulanmalıdır; önceki PR #137 CI sonucu yeni dalın CI sonucu yerine geçmez.
- Önceki taslak #149'daki `receipt` kontrollü sembolik bağlantı reddi korundu. GitHub üzerinde çalışan eski heartbeat düzeltmesi değiştirilmiyor.
- `pg_restore --list` tek başına veri kurtarma kanıtı değildir; gerçek kurtarma tatbikatı izole veritabanına yazdıktan sonra satırları karşılaştırır.
- Canlı üretim yedeği, sahip kimliği, güvenli kalıcı saklama ve Render yeniden başlatma kabul kriterleri halen açıktır.
