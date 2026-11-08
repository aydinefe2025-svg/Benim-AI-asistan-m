# CANO — Şifreli yedek kopyasını geri okuma doğrulaması

**Tarih:** 8 Kasım 2026 · Sürüm: sentetik güvenlik testli yardımcı araç

## Görev

`scripts/cano_render_rescue.py` ile bilgisayarda oluşturulmuş şifreli çok-kaynaklı PostgreSQL yedek klasörünün, ayrı bir depoya kopyalanıp tekrar indirildikten sonra **aynı baytlardan oluştuğunu ve AES-256-GCM anahtarıyla doğrulandığını** kontrol etmek. Bu araç yalnızca dosya okur. Canlı veritabanına bağlanmaz, geri yükleme yapmaz, kopyalama yapmaz, dosya yüklemez ve kaynak/kopya üzerinde değişiklik yapmaz.

## Kullanım

1. CANO kurtarma dosyalarını **önce** mevcut `python -m scripts.cano_render_rescue <ozel-kalici-klasor>` komutuyla, gerçek kaynak kimliğini ve gerekli gizli yerel ortam değişkenlerini ayarlayarak üretin. O işlemin gerçek veritabanına erişimi ve tam yedek oluşturduğu ayrıca doğrulanmalıdır.
2. Bütün şifreli `.canoenc` arşivleri, eşleşen `.receipt.json` dosyaları ve `cano-rescue-manifest.json` ile aynı klasör yapısını **bağımsız saklama sağlayıcısına** kopyalayın. Bu aracı kullanırken o kopyayı sağlayıcıdan yeniden indirip ayrı bir klasöre koyun.
3. Aynı, yalnızca sizin bilgisayarınızda bulunan `CANO_BACKUP_KEY_HEX` gizli ortam değişkeniyle çalıştırın. Anahtarı komut geçmişine, GitHub'a, Notion'a veya sohbete koymayın.
4. Depodan yeniden indirilmiş ayrı klasörde aşağıdaki komutu çalıştırın:

```powershell
python -m scripts.cano_offsite_readback "D:\CANO-ozel\yedek" "D:\CANO-test\uzaktan-geri-indirilen-kopya"
```

**Başarılı çıktının anlamı:** kaynak ve kopya manifestlerinin, listelenen bütün `.canoenc` ve `.receipt.json` dosyalarının SHA-256 eşleşmesi; kopyadaki her arşivin gerçek AES-GCM kimlik doğrulamasından geçmesi. Yanlış anahtar, bozuk dosya, eksik liste, fazladan şifresiz `.dump`, dizin kaçışı, symlink ve hardlink reddedilir.

**Kanıtın sınırı:** `copied_bytes_and_authentication_verified=true` yalnızca seçilen *iki klasörün* eşleşmesidir. `independent_provider_verified=false` ve `isolated_restore_verified=false` bilinçli olarak değişmez. Sağlayıcı bağımsızlığını ve gerçek PostgreSQL'de izole geri yüklemeyi ayrıca doğrulamadan felaket kurtarması bitmiş sayılmaz. `required_render_source_matched=false` ise tarihli Render veritabanının gerçekten yedeklendiği de kanıtlanmamıştır.

## Testler

- `python -m unittest discover -s tests -p test_cano_offsite_readback.py -v`
- Yerel test: **12 sentetik test başarılı**. Bunlar gerçek kullanıcı verisi içermez.
- Yerel geliştirme denemesindeki `scripts/cano_encrypted_backup.py` küçük test-yamacı **pakete alınmadı ve GitHub'a yazılmayacak**; GitHub CI gerçek mevcut `scripts.cano_encrypted_backup.verify_encrypted_backup` işlevini kullanır.
- Gerçek kullanıcı veritabanı dump'ı, farklı sağlayıcıya şifreli yükleme ve izole geri yükleme **bu raporla doğrulanmış değildir**.

## Takip

Render `research-library-persistent-db` ücretsiz PostgreSQL 18 son tarihi: **2026-12-02 21:11:49 UTC**. Canlı kaynağın kimliğini doğruladıktan sonra gerçek operatör yedeği ve bağımsız depodan kurtarma tatbikatı P0 açık iştir. Ücretli sağlayıcıya geçiş veya güvenlik duvarını herkese açma bu çözümün parçası değildir.