# CANO SPDX 2.3 — Kaynak düzeyi düzeltme ve güvenli birleştirme (pilot)

Bu araç **CANO araştırma kolundadır**, üretim sistemlerine bağlı değildir. İki SPDX 2.3 JSON belgesini, resmî 2.3.1 şemasıyla denetleyerek kaynak kimliklerini tutarlı biçimde birleştirmek için geliştirilmiştir.

## Gerekenler
- Python **3.13 veya üstü**, `jsonschema==4.26.0`
- Kullanıcının seçtiği **iki JSON dosyası** ve bunların **bağımsız güvenilir kaynaktan temin edilmiş SHA-256 özetleri**
- Kaynağa sabit Git blob hash'iyle erişim için GitHub'a HTTPS; kullanıcı SBOM dosyalarının içeriği dış servise **gönderilmez**
- Güvenilen ve yalnızca kullanıcının kontrolündeki dosya dizini; bu POSIX pilotu Windows'ta `O_NOFOLLOW` mevcut değilse güvenli biçimde **reddeder**

## Kurulum ve komut

```bash
python3.13 -m pip install 'jsonschema==4.26.0'
python3.13 research/opportunities/spdx_secure_merge_cli.py \
  --base input-base.spdx.json --source input-source.spdx.json \
  --base-sha256 <BASE_SHA256> --source-sha256 <SOURCE_SHA256> \
  --output merged.spdx.json
```

Beklenen SHA-256'yı aynı dosyadan hesaplayıp kendinizle karşılaştırmak yalnız bütünlüğü gösterir; **yayıncının kimliğini kanıtlamaz**. İmza doğrulama, ayrı trust anchor ve kanıtlanmış lisans uygunluğu bu pilotta henüz yoktur.

## Güvenli davranış

- `ACCEPT`: Yapısal SPDX şema ve ilişki / ID / PURL kapıları geçtiğinde `merged.spdx.json` **yeni** dosya olarak oluşturulur; önceden var olan çıktının üzerine yazmaz.
- `REVIEW_REQUIRED`: Farklı beyan edilen lisans gibi kaynak çelişkileri otomatik onaylanmaz, çıktı yazılmaz.
- `REJECT`: Çakışan kimlikler, bilinmeyen ilişki uçları, dosya veya şema hataları, doğrulanmamış harici `DocumentRef`, PURL eksikliği, bozuk JSON, symlink / hardlink veya beklenen hash uyuşmazlığında çıktı **yazılmaz**.
- Kaynak JSON'lar yerinde değiştirilmez; uygulama kopya üzerinde çalışır. **4 MiB** sınır ve normal dosya kısıtı uygulanır.

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

Yalnızca yapısal doğrulama ve bu fikstürler ile denetlenmiştir. Yayıncı imzası, tüm olası SPDX semantiği, Windows/NFS/SMB, büyük SBOM'lar, gerçek müşteri verisi ve canlı dağıtım **doğrulanmadı**. CI başarısı ticari güvence ya da otomatik birleştirme onayı değildir. Taslak PR #550 gözden geçirilmeden ana dala alınmaz.
