# CANO SPDX 2.3 — Kaynak düzeyi düzeltme ve güvenli birleştirme (pilot)

Bu araç **CANO araştırma kolundadır**, üretim sistemlerine bağlı değildir. İki SPDX 2.3 JSON belgesini, resmî 2.3.1 şemasıyla denetleyerek kaynak kimliklerini tutarlı biçimde birleştirmek için geliştirilmiştir.

## Gerekenler
- Python **3.13 veya üstü**, `jsonschema==4.26.0`
- Kullanıcının seçtiği **iki JSON dosyası** ve bunların **bağımsız güvenilir kaynaktan temin edilmiş SHA-256 özetleri**
- İndirilebilir ZIP, MIT lisanslı özgün modüllerin ve resmî SPDX şemasının **hash'leri doğrulanmış kopyalarını içerir**; ZIP'ten çıkarınca çalışmak için **ağ bağlantısı gerekmez**. Sadece GitHub kodu doğrudan çalıştırıldığında, kopyalar yoksa HTTPS ile sabit hash'li kaynaklar alınır. Kullanıcı SBOM içeriği dış servise **gönderilmez**
- Güvenilen ve yalnızca kullanıcının kontrolündeki dosya dizini; Linux'ta `O_NOFOLLOW` ile, **Windows'ta ayrı Win32 `CreateFileW(FILE_FLAG_OPEN_REPARSE_POINT)` okuyucusuyla** normal dosyaları kontrol eder; güvenilmeyen üst dizinler / ağ paylaşımları kapsam dışıdır

## Kurulum ve komut

```bash
python3.13 -m pip install 'jsonschema==4.26.0'
python3.13 spdx_secure_merge_cli.py \
  --base input-base.spdx.json --source input-source.spdx.json \
  --base-sha256 <BASE_SHA256> --source-sha256 <SOURCE_SHA256> \
  --output merged.spdx.json
```

Bu komut, **ZIP'i bir klasöre çıkartıp o klasörde çalıştırma** içindir. GitHub taslak PR klasörü içinden çalıştırırsanız betik yolu `research/opportunities/spdx_secure_merge_cli.py` olur. Çevrimdışı paket için `CANO_OFFLINE_ONLY=1` ortam değişkeniyle yalnız ZIP içindeki pinli kaynakların kullanılmasını zorunlu kılabilirsiniz.

Beklenen SHA-256'yı aynı dosyadan hesaplayıp kendinizle karşılaştırmak yalnız bütünlüğü gösterir; **yayıncının kimliğini kanıtlamaz**. İmza doğrulama, ayrı trust anchor ve kanıtlanmış lisans uygunluğu bu pilotta henüz yoktur.

### Windows PowerShell (çevrimdışı ZIP içinden)

```powershell
py -3.13 -m pip install jsonschema==4.26.0
$env:CANO_OFFLINE_ONLY = "1"
py -3.13 .\spdx_secure_merge_cli.py `
  --base .\base.spdx.json --source .\source.spdx.json `
  --base-sha256 "BAGIMSIZ_KAYNAKTAN_64_HANELI_SHA256" `
  --source-sha256 "BAGIMSIZ_KAYNAKTAN_64_HANELI_SHA256" `
  --output .\merged.spdx.json
```

ZIP'i güvenilir, size ait bir dizine açın. SHA değerleri yer tutucudur: **gerçek 64 haneli ve bağımsız doğruladığınız özetlerle değiştirin**. Sırf `Get-FileHash` ile aynı dosyadan hesaplamak dosyanın *yayıncı kimliğini* kanıtlamaz. İki dosyanın en fazla 4 MiB olduğu kabul edilir. Aynı ada sahip çıktı varsa üzerine yazılmaz. Windows 3.13 için özel CI, aracı gerçek dosyalarla sınar; genel Windows deposu testleriyle karıştırılmaz.

## Güvenli davranış

- `ACCEPT`: Yapısal SPDX şema ve ilişki / ID / PURL kapıları geçtiğinde `merged.spdx.json` **yeni** dosya olarak oluşturulur; önceden var olan çıktının üzerine yazmaz.
- `REVIEW_REQUIRED`: Farklı beyan edilen lisans gibi kaynak çelişkileri otomatik onaylanmaz, çıktı yazılmaz.
- `REJECT`: Çakışan kimlikler, bilinmeyen ilişki uçları, dosya veya şema hataları, doğrulanmamış harici `DocumentRef`, PURL eksikliği, bozuk JSON, symlink / hardlink veya beklenen hash uyuşmazlığında çıktı **yazılmaz**.
- Kaynak JSON'lar yerinde değiştirilmez; uygulama kopya üzerinde çalışır. **4 MiB** sınır ve normal dosya kısıtı uygulanır.
- Girdi dosyalarını güvenilir klasörlerde tutun; güvenilmeyen üst dizinlerdeki sembolik bağlantı / yarış durumlarına karşı kapsamlı dosya sistemi güvenlik garantisi verilmez.

## Gerçek upstream farkı

Kaynak: `MoriwakiYusuke/sbom-unifier`, commit `521f3b8ee6e301e847f7cb113517ba46831e2b28`, `merger.py` Git blob `afce37336f1d76f3e803f8eb4198f006c9125407`, [MIT lisansı](https://github.com/MoriwakiYusuke/sbom-unifier/blob/main/LICENSE). Kaynak dosyaları download sırasında hash ile kontrol edilir.

`spdx_source_patch.py` iki **kaynak kodu** sorununu yalnızca geçici çalışma alanındaki sabitlenmiş orijinal dosyaya uygular:

1. İç içe paket/dosya anotasyonlarına şemada bulunmayan `spdxElementId` eklenmesini kaldırır.
2. Yeni paketin her bağımlılığını ana pakete bağlayan ikinci akışı kaldırır; bunun yerine upstream'ın mevcut `merge_transitive_relationships` yordamı iki uç için PURL eşlemesi yapar.

Özgün upstream dosyaları ve kamuya açık repo **değiştirilmez**. Kaynak farkını izole olarak yeniden üretmek için `python research/opportunities/spdx_patched_acceptance.py` çalıştırın.

## Durum ve kapsam sınırı

`research/opportunities/spdx_validation_pipeline.py`: **özgün upstream kodu** + şema + çıkış temizleyici kıyaslama yolu (özgün ham çıktı uyumsuzluk kanıtı korunur).

`research/opportunities/spdx_patched_acceptance.py`: **özgün kaynağa doğrudan minimal düzeltme** + resmî şema + semantik kabul senaryoları.

`research/opportunities/spdx_secure_merge_selftest.py`: pilot komut satırı aracının I/O güvenliği ve sentetik birleşim testleri.

Yalnızca yapısal doğrulama ve bu fikstürler ile denetlenmiştir. Yayıncı imzası, tüm olası SPDX semantiği, Windows güvenilmeyen üst dizinleri, NFS/SMB, büyük SBOM'lar, gerçek müşteri verisi ve canlı dağıtım **doğrulanmadı**. CI başarısı ticari güvence ya da otomatik birleştirme onayı değildir. Taslak PR #550 gözden geçirilmeden ana dala alınmaz.
