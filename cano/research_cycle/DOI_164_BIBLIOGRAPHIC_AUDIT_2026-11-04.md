# CANO — beş DOI için yayın-kaynağı denetimi (4 Kasım 2026)

Bu çalışma, GitHub [Issue #164 / ikinci tarama](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/164#issuecomment-6632092882) tarafından kaydedilen beş DOI'nin **bibliyografik kimliğini** yayıncı ve akademik indeks kayıtlarıyla karşılaştırır. **Bu bir deney tekrarı, hakemlik denetimi ya da bilimsel doğruluk onayı değildir.** Çalışma, kaynak sayfalarının ayrı web incelemesiyle gözlemlenip JSON tanıklık dosyalarına kaydedildiği bir insan-destekli kaynak denetimidir; Python programı dış sitelere istek yapmaz.

## Sonuçlar

| DOI | Kaynak kanıtı | Bibliyografik sonuç | Bilimsel doğruluk / sonraki iş |
|---|---|---|---|
| `10.63328/ijcseai-v1ri1p3` | [IJCSEAI özgün dergi sayfası](https://ijcseai.com/view_issue.php?title=-Collaborative-Swarm-Intelligence-Framework-for-Multi-Agent-Scientific-Discovery-Systems) | DOI ve başlık yayınevi sayfasıyla eşleşti (2024 makalesi) | Dergi niteliği, deney verisi ve soyuttaki yüksek performans oranları ayrıca bağımsız sınanmalı. **Otomatik güven/deney onayı yok.** |
| `10.1038/s44387-026-00102-5` | [Nature / npj Artificial Intelligence](https://www.nature.com/articles/s44387-026-00102-5) | DOI ve başlık yayınevi kaydıyla eşleşti, 2026 araştırma makalesi | 10+ ajanlı sistem iddialarını kod, metot ve dış veriyle yeniden üretme ayrıca gerekli. |
| `10.3389/frai.2026.1820375` | [Frontiers özgün sayfa](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2026.1820375/full), [PubMed](https://pubmed.ncbi.nlm.nih.gov/42211174/) | DOI ve başlık iki kaynakta örtüşüyor; **Perspective** türünde | Mimari fikir için yararlı; **deneysel doğrulama çalışması değildir**. |
| `10.24963/ijcai.2025/538` | [IJCAI-2025 resmi bildiriler](https://ijcai.org/proceedings/2025/538) | DOI ve başlık bildiriler kaydıyla eşleşti | VO-MASD kodunun/SMAC benchmark'ının bağımsız tekrarına öncelik. |
| `10.1145/3788149.3788249` | [DBLP katalog kaydı](https://dblp.dagstuhl.de/rec/conf/csai/WangL25a.html) | DOI ve başlık akademik katalogda eşleşti; **yayıncı sayfası doğrudan incelenemedi** | ACM sayfası erişimi ve yöntem tekrarı gerekli. Finans alanı ana CANO bilim hedefi dışı: düşük öncelik. |

**Denetim sayıları:** 5/5 DOI için en az bir bibliyografik kayıt bulundu; 4 yayıncı/bildiri kaydı, 1 yalnız indeks; 1 kaydın ayrıca PubMed teyidi var. **0/5 bilimsel iddia bağımsız olarak yeniden üretildi.**

## Yazılım kanıtı

- `doi_evidence_gate.py`: başlık ve DOI bire bir eşleşmesi, URL'nin izinli HTTPS alan adı, kaynak türü doğrulaması, DOI / tanıklık tekrar kontrolü, sahte deney doğrulaması reddi.
- `doi164_candidates_2026-11-04.json`: Issue #164 tarama çıktısının izlenebilir DOI/başlık eşlemeleri.
- `doi164_source_attestations_2026-11-04.json`: Görülen kaynak sayfaları ve açık tür sınıflaması; dış URL'ler otomatik indirilmez.
- `doi164_review_result_2026-11-04.json`: Doğrulama çıktısı; her kaydın `scientific_claims_verified=false`, `automated_research_acceptance=false`.
- `test_doi_evidence_gate.py`: yanlış eşleşme, kötü URL, alan adı taklidi, kaynak türü değişikliği, mükerrerlik, sahte bilimsel başarı ve eksik kanıt güvenlik testleri.
- Birleştirilmiş CANO araştırma testleri: **174/174**, 4 Kasım 2026 yerel sandbox; `-W error::ResourceWarning`.

## Öncelikli gelişim sırası

1. IJCAI VO-MASD kodu ve yeniden üretilebilir değerlendirme komutlarını incelemek; küçük kontrollü veri kümesinde çalıştırmak.
2. Nature AgenticSciML makalesinin veri, kod, deney protokolü ve negatif kontrollerini belgelemek.
3. Frontiers perspektifini mimari tasarıma dönüştürürken iddiaları **öneri** olarak etiketlemek.
4. Diğer iki kaynak için yayınevi/katalog eşleşmelerini ve veri bulunurluğunu denetlemek; yeniden üretilemeyen oranları araştırma gerçeği olarak aktarmamak.

## Tekrarlanabilir doğrulama

```bash
cd cano/research_cycle
python -W error::ResourceWarning -m unittest discover -q
python doi_evidence_gate.py doi164_candidates_2026-11-04.json doi164_source_attestations_2026-11-04.json --output doi164_review_result_2026-11-04.json
```

Kaynak sayfası gözlemleri zaman içinde değişebilir; bu kod yeni yayıncı sayfalarını **kendiliğinden yeniden taramaz**. Yeni bibliyografik durum için yeniden kaynak gözlemi ve kanıt dosyasının sürümlenmesi gereklidir.