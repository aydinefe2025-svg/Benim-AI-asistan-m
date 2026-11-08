# CANO — Render PostgreSQL ücretsiz plandan kurtarma / bağımsız yedek

**8 Kasım 2026, denetim sonucu · Gerçek kayıt ve parola içermez.**

## 1. Doğrulanmış ortam

- Render çalışma alanı: `My Workspace`, `tea-dal81jjl550s73ci9bng` (kullanıcı tarafından seçildi).
- CANO ana Render web servisi: `benim-ai-asistan-streamlit`, `srv-dbiulm8473hc73amkjtg`. Dal: `fix/sqlite-backup-restore-20261031`, `autoDeploy=no`.
- Son doğrulanmış canlı dağıtım: `dep-dbnpnje7bikc73d72fk0`, commit `5b0335b84ca210f469f966fb3aa9c08e4a0fec4b`, durum `live`.
- Risk altındaki ücretsiz Render PostgreSQL: `research-library-persistent-db`, `dpg-dbkfp5bm8hqs73bba7u0-a`; **PostgreSQL 18**, durum `available`, son kullanım **2026-12-02 21:11:49 UTC** (Türkiye: 3 Aralık 00:11:49).
- Render veritabanı dış IP allowlist **boş**. Barındırılan Render MCP sunucusuyla salt-okunur SQL bağlanamadı. Bu nedenle Render şeması, gerçek tablo sayısı ve gerçek içeriği **okunamadı**. Kullanıcıdan habersiz genel IP erişimi açılmadı.
- Son 24 saat Render'ın saatlik toplulaştırılmış metriklerinde PostgreSQL aktif bağlantı sayısı `0` göründü. Bu bilgi DB'nin boş olduğunu **kanıtlamaz**.
- Neon ana proje: `benim-ai-persistence`, PostgreSQL 17, `assistant_pg`; **9 kullanıcı tablosu, toplam 30 mevcut satır** doğrudan salt-okunur sayım sorgularıyla doğrulandı: araştırma görevleri 1, görev olayları 1, laboratuvar kayıtları 2, özel koloni revizyonları 17, koloni anlık görüntüleri 2, özel bellek kayıtları 7; diğerleri 0.
- Neon PG18 staging proje: `cano-pg18-restore-staging`; `cano_restore_render_20261108` adlı DB gözlendi ve şu anda **0 kullanıcı tablosu** içeriyor. Hangi işlemle oluşturulduğu ve aktif kullanım amacı ayrıca teyit edilmeden içine veri yüklenmemelidir.
- **Render verilerinin Neon'a eksiksiz taşındığı doğrulanmamıştır.** Bu iki DB, birbirinin kanıtlanmış yedeği gibi gösterilmemelidir.

## 2. Kök neden

Render Free PostgreSQL için yönetilen yedek/snapshot desteği yoktur; ücretsiz web servisinde SSH, shell, tek seferlik iş ve kalıcı disk desteği yoktur. Boş dış IP izin listesi Render'ın **dış** SQL erişimini engeller, fakat aynı bölgede uygun Render hizmeti iç ağ URL'sini kullanabilir. Bu ortamda gerçek `pg_dump` çalıştırma, şifreli arşivi bağımsız sağlayıcıya aktarma ve izole gerçek geri yükleme kanıtı elde edilmedi.

Kaynaklar: https://render.com/docs/free ; https://render.com/docs/ssh ; https://render.com/docs/postgresql-creating-connecting

## 3. Hazırlanan operatör aracı (test edilmiş, üretimde çalıştırılmamış)

`cano_render_rescue.py` — Windows'ta GitHub deposunun `scripts/` klasörüne konur ve **mevcut**, daha önce test edilmiş `scripts/cano_encrypted_backup.py` AES-256-GCM akışlı `pg_dump` uygulamasını kullanır. Yeniden yazmaz. Python `cryptography` ve PostgreSQL **18+ pg_dump** istemcisi gerekir. Araç:

1. Render üzerinde veya geçici klasörde çalışmayı reddeder.
2. `research_library_persistent_db` dışında kaynak DB'yi, `*.render.com` dışında hostu, güvensiz `sslmode` değerini reddeder.
3. PostgreSQL 18+ sürümünü kontrol eder.
4. Kayıtlı **256-bit anahtarı** ve özel PostgreSQL URL'sini gizli terminal girdisi olarak ister; komut satırı argümanına/rapora eklemez. Terminal gizli giriş desteklemiyorsa durur.
5. Mevcut `cano_encrypted_backup.py` üzerinden **diske düz `pg_dump` yazmadan** şifreli `*.canoenc` + makbuz üretir, sonra ciphertext kimlik doğrulaması ve SHA-256 doğrulaması yapar.
6. Raporunda `independent_location_verified=false`, `restored_to_isolated_database=false` olarak kalır. Kendi başına buluta yükleme, dış IP açma, izin listesi kapatma veya canlı restore YAPMAZ.

Yerel sentetik test: `python -m unittest discover -s tests -p "test_cano_render_rescue.py" -v` → **OK (8 tests)**. GitHub Core CI test keşfi `unittest` kullandığı için bağımsız `pytest` bağımlılığı kaldırıldı. Yardımcı kaynak kod ve unittest testleri GitHub PR #437 kapsamında üretim kaynak dalına önerildi; canlı Render sürümüne dağıtılmadı ve gerçek veritabanında denenmedi. Bu testler gerçek kullanıcı verisinin yedeklendiği anlamına gelmez.

## 4. Bilgisayar başında uygulanacak güvenli prosedür

**Önkoşullar:** Yerel PostgreSQL 18+ `pg_dump` ve Python bağımlılıkları; GitHub deposu yerel klasörde; kurtarma aracının `scripts/` altında olması; 64 hex karakterlik rastgele üretilmiş yedek anahtarının **parola yöneticisinde ve ayrıca çevrimdışı güvenli kopyada** saklanması; ayrı/yedekli kalıcı hedef klasör. Anahtarı ChatGPT, GitHub, Notion, log ya da ekran görüntüsüyle paylaşmayın.

1. Windows bilgisayarda kopyası oluşturulmuş kalıcı/harici sürücüde bir klasör hazırlayın (örnek `E:\\CANO_BACKUPS`). Sadece `C:` geçici klasörü veya Git deposu yeterli değildir.
2. PowerShell 7'de GitHub depo köküne gidip `py scripts\\cano_render_rescue.py --destination "E:\\CANO_BACKUPS" --preflight` komutunu çalıştırın. `preflight=PASS` gerçek yedek değildir.
3. Render Dashboard'da yalnızca bu PostgreSQL'in Networking/IP Allowlist bölümüne **bilgisayarınızın o anki dış IPv4 adresini `/32`** olarak geçici ekleyin. `0.0.0.0/0` kullanmayın. Render PostgreSQL **External Connection URL** bilgisini özel olarak alın; bunu sohbete göndermeyin.
4. `py scripts\\cano_render_rescue.py --destination "E:\\CANO_BACKUPS" --confirm-independent-storage` çalıştırın. URL ve önceden saklanmış 64 haneli anahtarı gizli istemlere girin. Araç `.canoenc`, `.receipt.json`, hash ve şifre doğrulama durumunu üretir.
5. Başarılı ya da başarısız olması fark etmeksizin **hemen** Render allowlist'teki geçici `/32` kaydını kaldırıp listenin tekrar boş olduğunu doğrulayın.
6. `.canoenc` ve `.receipt.json` dosyalarının **bir kopyasını başka sağlayıcının özel kalıcı depolamasına** aktarın, geri indirerek SHA256 ve şifreli doğrulamayı tekrar yapın. Anahtarı bu dosyalarla aynı konumda saklamayın.
7. Yalnızca ayrı, boş ve uygun `cano_restore_*` PostgreSQL hedefine **orijinal şifreli arşivle izole geri yükleme** yapın; gerçek tablo/satır ve hesap-kapsamlı hash eşleşmesini kontrol edin. Yanlış kaynak veya hedef alias'ı varsa işlemi durdurun; canlı servis DB'sine `pg_restore` çalıştırmayın.

Başarılı kabul için **dört ayrı kanıt** gerekir: (a) gerçek Render `pg_dump` ve doğrulanmış şifreli makbuz, (b) farklı sağlayıcıdan geri indirilmiş byte-eşit dosya, (c) boş izole hedefe gerçek restore, (d) kaynak/hedef tablo ve kayıt kıyası. Bunlar henüz **tamamlanmadı**.

## 5. Hâlâ bekleyen iş

**P0:** Render PostgreSQL verisi gerçekten dolu mu, Neon ile aynı mı? Dış erişim kilitli olduğundan doğrulanamadı. Bu, verilerin Render'dan bağımsız olduğunun tespiti için `pg_dump` önceliğini değiştirmez.

**P0:** Gerçek şifreli arşiv / farklı sağlayıcı / kurtarma kanıtı yok.

**P1:** Her başarılı gerçek kurtarma sonrasında kullanıcıya özel gizli veri kaydetmeyen durum raporunu güncelle ve dış IP allowlist'in kapalı kaldığını doğrula.

## 6. Kayıt ilkesi

Bu rapor yalnızca API metadatası, şifresiz sayım ve hazırlanan kaynak kod testlerine dayalıdır; şifre, bağlantı URL'si, gerçek kayıt gövdesi ve PostgreSQL dump barındırmaz. Canlı veritabanında mutasyon veya Render dağıtımı yapılmadı.