# CANO — izinli bilimsel metaveri toplama ve inceleme kuyruğu

**Sürüm:** 4 Kasım 2026 · **Amaç:** bilimsel kaynağı bulma ve DOI'leri kullanıcı incelemesine sunma. Bu aşama bilimsel iddiaları doğrulamaz.

## Veri akışı

1. Günlük GitHub Actions iş akışı tek bir konuyu seçer (`robotics`, `materials`, `biology`, `history`, `artificial_intelligence`).
2. Crossref ücretsiz API'sine bir tek sabit-HTTPS sorgu yollar. En fazla 5 sonuç alır; toplam yanıtı 512 KiB ile sınırlar. Yönlendirmeler ve güvensiz DOI biçimleri reddedilir.
3. DOI, başlık, yayın tarihi ve yayın türü dışında makale tam metni ve abstract alınmaz. Sonuç `pending_review` durumunda saklanır.
4. GitHub **issue #164** önceki DOI işaretleri için okunur. Yalnızca yeni DOI'ler tek yorumla yazılır, sonrasında geri okunur. İşlem tekrarlanırsa aynı DOI tekrar eklenmez.
5. GitHub Actions ham metaveriyi inceleme artifaktı olarak 14 gün saklar. Kalıcı kaynak indeksi issue yorumlarıdır.

## Manuel ve otomatik çalışma

- GitHub Actions: `.github/workflows/cano-crossref-discovery.yml`; PR için 17 çevrimdışı güvenlik/yineleme testi, `push(main)`, günlük `schedule` ve elle `workflow_dispatch` için canlı tarama.
- Yerel, salt-okunur toplama: `python crossref_discovery.py --topic robotics --rows 5 --output crossref_pending_review.json`
- Yalnızca yetkili depoda yorum: `GITHUB_REPOSITORY`, `CANO_REVIEW_ISSUE=164`, `GITHUB_TOKEN` ortam değişkenleriyle `python github_review_sink.py crossref_pending_review.json`.
- Sırları hiçbir zaman koda, log dosyasına veya rapora yazmayın. GitHub `GITHUB_TOKEN` kısa ömürlü yerleşik kimlik doğrulamasıdır.
- HTTP 429, ağ hatası, veri şeması sapması ve GitHub erişim sorunu başarısız çıkar. Sessizce başarılı sayılmaz; sonraki günlük döngü yeniden denenebilir.

## Güvenlik sınırları

- İzinli tek uzak alan Crossref `api.crossref.org`. Kaynak URL'leri keyfi açılmaz. Özet/tam metin alınmaz.
- İkinci uzak alan yalnızca GitHub API `api.github.com` ve yalnızca sabit issue yorumları rotası.
- İzin verilen yazma yüzeyi tek kayıt sayfasının yorumlarıdır. Kod, README veya üretim veritabanı canlı döngüde değiştirilmez.
- Günlük koşu başına en fazla 1 Crossref sorgusu, 5 DOI, 1 GitHub yorumu. İstekler eşzamanlı yürütülmez. Dedup geçmişi 1000 yorumun üzerine çıktığında sistem hata vererek durur; tarihçe eksikken tekrar yazmaz.
- GitHub Actions bir `concurrency` grubuyla çakışmaları önler.
- DOI metaverisi **bilimsel kanıt** değildir. Alan uzmanı, makale ve veri kaynaklarını bağımsız doğrulamadan sonucu kabul etmez.

## Bağımsız kanıt gereksinimleri

- Yerel 17 test ve tüm önceki yazılım testlerinin geçmesi.
- GitHub PR CI çalışması ve ana dala alınmasının kaydedilmesi.
- GitHub Actions `push(main)` koşusunda Crossref canlı HTTPS sorgusu, issue yorumu ve geri-okuma sonucu.
- Geçmiş DOI kaydının ikinci koşuda tekrar eklenmediğinin doğrulanması.

## Kaynak

Crossref REST API: https://www.crossref.org/documentation/retrieve-metadata/rest-api/

Crossref API erişimi ve hız sınırları: https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
