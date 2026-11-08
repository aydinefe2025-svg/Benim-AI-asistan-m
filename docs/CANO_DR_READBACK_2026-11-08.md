# CANO P0 — Şifreli tam PostgreSQL yedeği sonrası bağımsız veri karşılaştırması

**Kapsam:** Bu doküman, operatörün kendi cihazında ve kendi erişim bilgileriyle yapacağı geri yükleme kabulüdür. **Yedek burada alınmaz.** Gerçek kullanıcı verisi, DB URI'si, parola veya AES anahtarı GitHub/Notion/ChatGPT ile paylaşılmaz.

## Sıra ve sınırlar

1. Canlı kaynağı doğru belirle: CANO ana Neon PostgreSQL'i ile ayrı Render Free PostgreSQL 18 veritabanını **aynı kabul etme**. Uygulamanın hangi bağlantıyı kullandığını doğrula.
2. Mevcut `scripts/cano_encrypted_backup.py` ile gerçek `pg_dump` verisini düz metin arşiv yazmadan AES-256-GCM olarak **kullanıcı kontrolündeki farklı sağlayıcı/özel fiziksel depoya** al. 32 baytlık şifreleme anahtarını hedef arşivden ayrı, offline sakla.
3. `verify` komutuyla şifreli arşivi ve receipt'i doğrula. Ardından yalnız yeni ve boş `cano_restore_*` PostgreSQL veritabanında, mevcut fail-closed `restore-isolated` adımıyla geri yükle. Aynı canlı veritabanına asla restore yapma.
4. Ayrı kaynak ve hedef veritabanına erişebilen **güvenilir operatör bilgisayarında**, gizli oturum ortamında `CANO_AUDIT_SOURCE_DATABASE_URL` ve `CANO_RESTORE_DATABASE_URL` değişkenlerini ayrı URL'lere ayarla. Parolaları komut satırı argümanı, dosya veya komut geçmişine yazma.
5. Repo kökünden `python -m scripts.cano_dr_compare` çalıştır. Python bağımlılığı `psycopg[binary]` paketidir (repo `requirements-persistence.txt` dosyası).
6. `status=MATCH`, `verified_tables=9`, `schema_metadata_equal=true`, `mismatched_tables=[]` ve satır sayısı kıyasının geçtiğini doğrula. İşlemden sonra ortam değişkenlerini temizle, şifreli arşivin kalıcı dış kopyasını ve bağımsız anahtar yedeğini yeniden kontrol et.

## Doğrulama algoritması

- Kaynak ve hedefe **farklı PostgreSQL bağlantıları** açar. Hedef adı `cano_restore_*` olmalı; aktif kaynakla veya aynı fiziksel DB kimliğiyle çakışan hedef reddedilir.
- Her bağlantı `REPEATABLE READ READ ONLY` işlemi içinde çalışır, veritabanı adını sunucudan yeniden okur; SQL yazımı çalıştırmaz.
- 9 beklenen CANO uygulama tablosunun **kolonlarını, constraint/index metadata bilgisini, RLS policy ve tablo RLS bayraklarını** kıyaslar. Beklenen tablolardan biri eksikse durur.
- Her satır PostgreSQL'de SHA-256 özetlenir; uygulamaya yalnız bu özetler ulaşır, ham satır içerikleri veya owner anahtarları yazdırılmaz. Sıralı özet akışı ile iki tarafta içerik karşılaştırması yapılır. Kayıt sayısı aynı ama içerik farklıysa `DIFFERENT`.
- Çıkış kodları: 0=MATCH; 2=DIFFERENT; 3=BLOCKED/doğrulanamadı. Sonuç **tam SQL rollerinin, extension'ların veya işlevlerin kurtarıldığı** iddiası değildir; tam DB restore kanıtı ayrıca gereklidir.
- Ayrı veritabanları arasında tek global PostgreSQL snapshot olmadığı için çok yoğun canlı yazım sırasında fark görülebilir. Canlı veriyi dondurmak veya kapatmak için bu araç hiçbir işlem yapmaz. Operatör restore anına uygun kaynak tutarlılığı sağlamalıdır.

## Sentetik kanıt

PR #431 testleri eski sahte başarılı davranışı RED olarak yakaladı. PostgreSQL 17/18 üzerinde **9 tablo ve 18 sentetik satırla** eşleşme; laboratuvar içeriği değişince `DIFFERENT`, fazladan indeks olduğunda şema uyuşmazlığı ve tehlikeli hedef reddi doğrulanır. Gerçek CANO PostgreSQL'e, Render'a veya parola/anahtarlara dokunulmaz.

## Açık P0

Dış depoda **gerçek, geri yüklenmiş ve kıyaslanmış** şifreli PostgreSQL arşivi henüz bu PR'ın kanıtı değildir. Sadece kod ve sentetik test başarılarıyla bu görev kapatılamaz. Kullanıcı verisi hiçbir GitHub Actions testine yüklenmez.
