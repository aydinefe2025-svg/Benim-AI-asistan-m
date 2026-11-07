# CANO P0 — canlı yedekleme bekleme süresi ve yanlış hedef koruması

**Tarih:** 7 Kasım 2026
**Kaynak sistem:** `aydinefe2025-svg/Benim-AI-asistan-m`, PR #399 ile gelen `scripts/cano_encrypted_backup.py`.

## Üretim riski

1. Önceki şifreli yedekleme, `pg_dump` stdout hattını bloklayan `read()` ile tüketiyordu. `wait(timeout=1800)` satırına hiç ulaşamayan, çıkıştan önce takılmış bir `pg_dump` işlemi teorik olarak sınırsız kalabilirdi. Bu, otomatik yedekleme tekrarlarını durduran gerçek bir operasyon riski.
2. Geri yükleme hedefi yalnız `DATABASE_URL` kaynağıyla karşılaştırılıyordu. CANO'nun `AGENT_TASK_DATABASE_URL` gibi başka kayıt kaynağı ile aynı veritabanı yanlış biçimde `cano_restore_*` adını taşıyorsa ilk kontrol eşleşmeyi kaçırabiliyordu. Çalıştırılacak asıl veritabanı açıkça seçilmeden restore'a izin vermemek gerekir.

## Değişiklik

- `pg_dump` akışı artık **en fazla dört adet 256-KiB blok** tutabilen kuyruktaki ayrı okuma işçisi üzerinden şifrelenir. `time.monotonic()` tabanlı uçtan uca `max_seconds` (varsayılan 1800) hem veri gelmeme hem işlem sonunu bekleme aşamasını kapsar. Süre dolunca alt süreç öldürülür; geçici şifreli dosya ve geri dönüş makbuzu yayımlanmaz. Düz metin döküm dosyası yine oluşmaz.
- `restore_to_empty_database` tanımlı CANO kaynak URL değişkenlerini inceler; host, varsayılan port (5432) ve database adı aynıysa **decryption, psql ve pg_restore başlamadan önce** reddeder. `localhost` / `127.0.0.1` / `::1` eşdeğer normalize edilir. Bu kontrol, tüm olası üretim hedeflerini keşfedebileceği iddiasında değildir; bilinmeyen env adları için ayrıca operasyonel kontrol gerekir.
- Gerçek bağlantı URL'leri, AES anahtarı veya kullanıcı verileri belgeye ve GitHub'a eklenmez.

## Gözlenen RED → GREEN

`python -W error::ResourceWarning -m unittest discover -s tests -p 'test_cano_encrypted_backup.py' -v`

- RED: yeni `max_seconds` olmaması `TypeError`; kaynak alias testi `decrypt_to_sink` çağrısını yakalayıp **FAIL** verdi.
- GREEN: **10/10 test**, `ResourceWarning` hata sayılarak başarılı. Gerçek PostgreSQL sunucusu burada yok; testleri kendi canlı veritabanında değil izole sentetik `pg_dump` üreticisi üzerinde çalıştırdık.

**Bağımsız kabul kapısı:** GitHub Actions `.github/workflows/cano-encrypted-offsite-dr.yml` PostgreSQL 17 ve 18 ile gerçek `pg_dump` → şifreleme → boş ayrı DB restore → satır eşleme sürecini tekrar çalıştırmalı. PR yeşil olmadan üretime terfi edilmemeli. Üretim Neon'dan gerçek offsite şifreli kopya ve farklı sağlayıcıda geri yükleme yapılmış değildir.

## Gerçek üretim verisinin güvenliği

Yüklenmesi gereken gerçek kopyanın şifreli biçimde sadece kullanıcı kontrollü farklı saklama alanında kalması gerekir. Kaynak URL ve 256 bit anahtar GitHub, Notion, CI, sohbet veya ChatGPT Library'ye aktarılmaz. Mevcut Neon snapshot ve kopya dalları **aynı sağlayıcının içindeki** kurtarma olanaklarıdır. Ücretli kaynak otomatik başlatılmaz.
