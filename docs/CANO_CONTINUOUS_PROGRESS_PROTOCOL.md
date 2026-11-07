# CANO — Sürekli Gelişim, Kanıt ve Kalıcı Devam Protokolü
**Karar tarihi:** 2026-11-07 (Europe/Istanbul)
**Kapsam:** ChatGPT/Codex destekli CANO geliştirme ve ayrı disiplinlerdeki araştırma yürütmeleri; GitHub kaynak gerçekliği, Notion kanıt ve ana kütüphane, planlı görevler.
**Yürütme:** Bu belge iş emridir; kendisi yürütücü/scheduler oluşturmaz. Her otomasyon/ajan bu kuralları kendi erişebildiği ve yetkili olduğu çalışma ortamında uygular.

## Temel karar
Kullanıcı aynı "devam et / çöz / kaydet" komutunu tekrar vermek zorunda kalmasın. Yetkili ve ücretsiz kaynaklar erişilebilir olduğunda her tetiklenen çalışma, açık bir somut işi tamamlamak veya ölçülebilir biçimde ilerletmek için girişimde bulunur. Planı tekrar yazmak bir işin tamamlanması değildir. Engelde durma: kök nedeni kaydet, güvenli alternatif yola veya *başka açık bağımsız işe* geç. Araştırma çalışması devreye alınmadan önce geçmiş kanıtı kontrol et. Konular arası karışıklık veya doğrulanmamış tamamlanma beyanı yapma.

## İş öncesi zorunlu uzlaşma
1. Önce `docs/CANO_MASTER_REQUIREMENTS_2026-11-04.md`, GitHub Issue #95, en güncel ilgili PR/CI/branch, Notion konu kaydı ve son kanıt manifestini oku. Yereldeki `AGENTS.md` ve bu dosyayı uygula.
2. İş kimliğini **topic_key + goal_key + acceptance_test** olarak belirle; aynı anahtar için halihazırda yürütülmekte/başarılmış bir işi yeniden üretme. Mümkünse GitHub Issue/PR ve Notion bağlantısına bağla.
3. Etiketle: `not_started`, `running`, `blocked`, `tested`, `ci_verified`, `live_verified`, `archived_verified`. `blocked` veya `tested` = tamamlandı değildir.
4. En yüksek etkili, uygulanabilir ve başka ajanla çakışmayan işi seç. P0 güvenli geri kazanım, veri kaybı ve mevcut üretim açıkları önceliklidir. Bilimsel işler kendi kanıt standardına göre değerlendirilir; başka projenin başarı testi bu projeye taşınmaz.

## Her gerçek çalışma döngüsü
`READ → DEDUP/CLAIM → BUILD OR RESEARCH → REPRODUCIBLE TEST → INDEPENDENT CHECK → COMMIT/RECEIPT → ARCHIVE/READBACK → NEXT`
- Deney için kaynak sürümü, tarih/saat, kod sürümü, bağımlılıklar, seed, komutlar, çıktı özeti, kontrol grubu ve başarı/başarısızlık yaz.
- Kod için mümkünse başarısızlık örneği (RED), düzeltme (GREEN), regresyon ve ilgili platform testlerini kaydet. Üretime aktarım için ayrıca canlı hizmet kanıtı gerekir.
- Bilim için birincil kaynak, tam metin/özet ayrımı, kullanılan veriler, karşı kanıt, belirsizlik ve tekrar üretilebilir hesap şart. Simülasyonu fiziksel keşif gibi sunma.
- Kayıt: kaynak bağlantıları ve dosya SHA-256, kaynak dal/SHA, CI run URL, ilgili Notion sayfası ve kütüphane yolu; yazıdan sonra geri okuma. Kayıt erişilemiyorsa `archive_unverified` diye belirt, asla kaydedildi deme.
- Başka otomasyon aynı iş üzerinde çalışıyorsa ikinci bir kayıt veya PR açma; yeni/ayrı bir iş seç. Yeni olgu yoksa tekrarlayan rapor yazma.
- İş kesilirse son checkpoint ve sonraki tek eylemden devam et; yeni oturumu sıfırdan başlatma. Eski kanıtı yeni koşu gibi sunma.

## Tekil kanıt makbuzu (örnek JSON alanları)
```json
{"topic_key":"robotics.organism-lab","goal_key":"self-build-cad","run_id":"unique-run","date_utc":"ISO-8601","input_refs":[],"source_sha":"sha-or-null","artifact_paths":[],"sha256":{},"test_command":"exact-command-or-null","test_results":{},"claim_level":"tested","notion_url":null,"library_path":null,"readback_verified":false,"remaining_gap":[],"next_action":""}
```
Bu şema bir *önerilen veri sözleşmesidir*, mevcut bütün yazılımların bunu yazdığı iddia edilmez. Gizli anahtar, kullanıcı veri satırları ve OIDC tokenları hiçbir makbuza konmaz.

## Bağımsız konu şeritleri (kapsamı silme, konuları birbirine karıştırma)
- `cano.core`: çoklu ajanlar, kalıcı hafıza, görev kuyruğu, Codex/GitHub/Render/Neon, güvenlik, yedek-kurtarma, ölçülebilir öğrenme; üretim ve sentetik CI ayrı.
- `organism.digital`: sınırlı dijital organizma, evrim/kalıtım, başabaş kontrol grupları, jenerasyon görev başarısı; fiziksel canlı değil.
- `robotics.self-build`: sanal montaj → parametrik CAD → mesh/özellik testi → üretime hazırlık; ilk CAD v1 kanıtı Library `/Research-Evidence/Organism-Lab-2026-11-07/CANO_Self_Build_CAD_v1_2026-11-07.zip`. Fiziksel üretim ve robot gövdesi henüz kanıtlanmadı.
- `research.global`: Küresel Keşif Ağı, Ruflo, GitHub gözleri, güvenlik ve yeni disiplinlerarası keşifler.
- `research.opportunities`: Dünya Fırsat Taraması, bilimsel/açık kaynak fırsatları, maliyet/uygulanabilirlik değerlendirmesi.
- `research.robotics`: robotik simülasyon, biyomimetik, batarya ve hücresel *hesaplamalı* modeller; ayrı veri ve testler.
- `research.history`: Tarihin İz Sürücüleri, tarihî teknolojiler, Cezerî, Tesla/Ferraris, Fatih dönemi, İskenderiye, Atlantis/Mu; kanıt ve spekülasyon ayrımı, tarih ve kaynak bağlantıları.
- `research.neutron-star`: PSR J0740+6620 NICER/XMM/Salmi, EOS, X-PSI, TOV, dönme, Love/Λ, A01.01.50 ve A01.01.51 geçmiş kayıtları. **Bağımsız şerit**: Dünya Fırsat Taraması/Küresel Keşif Ağı otomasyonlarının mevcut 'nötron yıldızı hariç' kuralını değiştirme; nötron yıldızı ayrı araştırma oturumunda yürütülür.
- `research.other`: geçmiş konuşma ve ana kütüphanedeki diğer doğrulanmış başlıklar; kanonik envanter ve birincil kaynak bulunmadan yeni başarı kaydı ekleme.

## Süreklilik ve güvenlik sınırları
- ChatGPT konuşmalarını tek merkezden otomatik değiştirebildiğini veya Codex'in farklı oturumlarına anında komut iletebildiğini iddia etme. Depoyu okuyan Codex ajanları için kök `AGENTS.md`, planlı ChatGPT görevleri için otomasyon promptları, Notion için ana arşiv kayıtları ayrı dağıtım mekanizmalarıdır.
- Erişilebilir yerel hesaplama ve geri kazanılmış/sahip olunan donanım değerlendirilebilir. Başkalarının fabrika/hesap/robot/cihazlarına izinsiz erişim, rastgele ağ yayılımı, sınırsız kopyalanma, sessiz ödeme, gizli sırların açığa çıkması, üretim verisinin kayıp riskiyle değiştirilmesi yok.
- Sürekli çalışma yalnızca mevcut **zamanlanmış tetiklemeler** ve fiilen çalışan işçilerce gerçekleşir; arka planda sonsuz faaliyet varsayma. Her işe mümkünse maliyet/süre/kaynak kotası ve durdurma olanağı ekle.
- Kullanıcı yalnızca gerçek yeni sonuç, kesin sınır ve sonraki önemli eylem görsün. Sayısız mikro-varyant veya boş 'devam' raporu üretme.

## Bitirme/kabul kapısı
Her dosya ve canlı sonuç doğru kaynakla eşleşmeli. `done` ancak ilgili kabul testi + bağımsız readback + ilgili GitHub CI/üretim testi (gerekliyse) + Notion/Library arşiv doğrulaması gerçekleşince yazılır. Bileşen düzeyinde `done`, projenin tamamının bittiği anlamına gelmez.

**Kanonik bağlantılar**
- GitHub: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m
- Üretim kabul listesi: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/95
- Notion ana kütüphane: https://app.notion.com/p/4022bd61682a8144b15de6f7c640978a
