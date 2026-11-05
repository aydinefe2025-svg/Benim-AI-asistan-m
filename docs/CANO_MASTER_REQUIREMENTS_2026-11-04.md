# CANO ana özellik / gereksinim envanteri — 4 Kasım 2026

**Güncellik:** İlk envanter 4 Kasım 2026 tarihli; 5 Kasım kod uzlaştırması aşağıdadır. Tarihli canlı/CI kayıtları kendi tarihleri için kanıttır; son sürümün canlı doğrulaması sayılmaz.

**Kaynak kapsamı:** Kullanıcının geçmiş istekleri ve 4 Kasım 2026'da bağlı GitHub/Render incelemesi. Bu belge tüm mümkün teknolojilerin envanteri değil, **şimdiye dek istenmiş başlıca özelliklerin tek takip haritasıdır**. Tarihler ve durumlar yeni kanıtla revize edilir. Ana izleme kaydı: [GitHub #95](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/95); [Notion araştırma kütüphanesi](https://app.notion.com/p/4022bd61682a8144b15de6f7c640978a).

**Durum anahtarı:** **CANLI TEST** = Render uygulamasında gözlemlenmiş kullanıcı akışı; **KOD/CI** = uygulama ve GitHub testleri var ama ilgili üretim senaryosu bağımsız doğrulanmamış; **KISMİ** = bazı parçalar var; **AÇIK** = tam çalışır uygulama kanıtı yok; **SİMÜLASYON** = fiziksel/biyolojik/özerk gerçekleme değil. Bu etiketler başarı yüzdesi değildir.

## 1. Çekirdek zekâ, ajanlar ve güvenilir görevler

| İstek / yetenek | Bugünkü doğrulanabilir durum | Kabul ölçütü / açık iş |
|---|---|---|
| Türkçe asistan, Groq/Google model sağlayıcıları | **CANLI TEST:** Streamlit/Groq yanıt verdi; provider_config.py iki sağlayıcıyı destekler | Her sağlayıcı için yapılandırılmış bağlantı ve hata testleri |
| Kurucu CANO + uzman ajanlar | **CANLI TEST:** 1 kurucu + 3 uzman kaydı ve tek uzman görev yanıtı gözlendi; kayıt bağımsız işlem/model değildir | Gerçek ayrı işçi zamanlaması ve görev sahipliği |
| Uzmanları otomatik, çoğalarak büyütme | **KOD/CI:** grow_specialists; kota 12, izinli ve idempotent | Sahip olunan hesap/cihazlarla güvenli, limitli ölçekleme; gizli izinsiz yayılım yok |
| Planlama→araştırma→eleştiri→sentez | **CANLI TEST:** dört model çağrısı, ekranda dört çıktı | Görev kalitesi kıyası, ölçülen doğruluk, kısa/uzun çıktı beklentisi |
| Kesilen görevden devam / aşama checkpoint | **KOD/CI:** PR #108; LIVE dağıtım; geri kazanma birim testleri | Canlı bağlantı kesme/geri dönme tatbikatı, çağrı bütçesi doğrulama |
| Kimliği belirli, idempotent kuyruk; tekrar deneme; işçi bütçesi | **KOD / ARAYÜZ ENTEGRASYONU:** owner PostgreSQL kuyruğu, tekil anahtar, transactional claim, deneme bütçesi ve olay günlüğü mevcut; yürütme kullanıcı tetiklemeli tek çağrı | Canlı hesapta tekrar gönderme, iki işçi, kesinti ve kalıcılık tatbikatı; otomatik yürütücü/DAG henüz yok |
| Görev alt parçalama / DAG / öncelik / süre / bağımlılık | **KISMİ:** araştırma planlayıcı rolü ve görev listesi | Bağımlılık çözme ve aşama sonuçlarına dayalı yürütme |
| Hata ayıklayan onarımcı ajanlar | **KISMİ:** test, kayıt, rol ve hata kurtarma var | Hata sınıflaması→minimal PR→CI→geri alma→kanıtlı dağıtım döngüsü |
| İkinci bağımsız ajan / Ana Kraliçe | **KOD / CI TANIMI:** SQLite yanında kimlik doğrulamalı PostgreSQL epoch fencing primitive ve sentetik entegrasyon workflow’u var; uygulama işçilerine bağlı değil | Gerçek işçi yazımlarında aynı transaction içinde fence, iki düğüm split-brain/failover ve canlı doğrulama |
| Çoklu LLM ve yerel Ollama / OpenCode / Kody / Codex orkestrasyonu | **KISMİ:** Groq/Google yanında Ollama chat ve yerel CLI araştırma entegrasyonu var; kuyruk/uzman/komuta merkezi Groq callback kullanıyor | Ortak sağlayıcı katmanı, izinli uçtan uca görev devri; yerel istemci bağlıyken doğrulama |
| Sürüm değerlendirme, geliştirme ve otomatik geri alma | **KISMİ:** agent_evolution.py yerel değerlendirme ve rollback kapısı | Canlı deney, tarafsız ölçüm, insan onaylı terfi ve üretim rollback'i |
| Her sürümün testli ve sürülebilir olması | **KISMİ:** Windows/Linux GitHub CI, PR ve Render dağıtımları | Tam E2E regresyon, kalıcılık, yük, güvenlik, rollback |

## 2. Öğrenme, hafıza ve araştırma

| İstek / yetenek | Bugünkü doğrulanabilir durum | Kabul ölçütü / açık iş |
|---|---|---|
| Her deneyden öğrenme / sürekli gelişim | **KISMİ:** accepted feedback dersleri prompt'a getiriliyor; model ağırlıkları eğitilmiyor | Bellekli/belleksiz görevler için doğruluk, geri çağırma ve gerileme testleri |
| Kalıcı kullanıcı hafızası / oturumlar arası devam | **KISMİ:** tarayıcı notları, SQLite, JSON yedek ve isteğe bağlı owner PostgreSQL | Kimlik doğrulamalı, otomatik, şifreli kalıcı veri ve sunucu restart tatbikatı |
| Otomatik yedek ve güvenli geri yükleme | **KISMİ:** JSON export/import; PR #106 ve #109, PostgreSQL sahip snapshot sınıfı | Gerçek backup→readback→restart→restore; başarısızlık alarmı |
| Birleştirilmiş Notion ana kütüphane ve kanıt defteri | **KISMİ:** ayrı Notion raporları gerçek yazılıp geri okunmuş | Her görevde versioned manifest, çift yönlü indeks, dedup ve kaynak bağlantısı |
| Bilgi grafiği / kavramlar arası keşif, çelişki tespiti | **AÇIK:** tam güvenilir grafik çalışması kanıtı yok | Kaynak/provenans, ilişki ve tarih alanları, çelişki incelemesi |
| Gerçek zamanlı web araştırması | **KISMİ:** Wikipedia/Crossref kaynak aday bulucu kodları var | Özellikle bilimsel birincil kaynakları açıp inceleyerek kanıt notu üretmek |
| Kaynakları otomatik kanıtla karşılaştırma | **KISMİ:** Crossref adayları, Europe PMC metin/özet okuma, birebir alıntı denetimi ve sözcük/olumsuzluk tabanlı iddia-pasaj karşılaştırması kod/arayüzde var; bilimsel doğruluk veya entailment kanıtı değil | Etiketli iddialarda doğruluk/karşı kanıt kıyası, bağlam ve kaynak kalitesi; canlı okuma ve kayıt geri okuma |
| Hipotez→deney planı→fizik testi→yeniden üretim | **KISMİ:** araştırma iş akışları ve ayrı bilimsel işler var | Gerçek koşum kimliği, veri/parametre/cihaz/CI ve sonuç doğrulaması |
| Tarihin İz Sürücüleri / icatlar / İskenderiye / Atlantis-Mu | **KISMİ:** ayrı günlük keşif görevi, geçmiş araştırma | Birincil kaynak, kronoloji, delil ağırlığı, çözülemeyen sorular ve Notion |
| Evren/astronomi, PSR J0740+6620 EOS/NICER/XMM | **KISMİ:** A01.01.50 ayrı Colab/Drive denetim çalışması mevcut | Full EOS posterior, prior düzeltmesi, X-PSI bağımsız test; 12.88 GB yerel arşivi yeniden indirme |
| Dünya Fırsat Taraması, Küresel Keşif Ağı, Robotik ve Hücresel Keşif | **KISMİ:** ayrı günlük planlı tarama görevleri var | Kaynak kalite kapısı, eşleştirme, tekrar azaltma, doğrulanmış kütüphane kaydı |
| GitHub/GitLab/Notion kaynak tarama, uyarı, günlük öğrenme | **KISMİ:** mevcut otomasyonlar/bağlı kaynaklar | Tek plan, per-task izlenebilirlik, gerçek hata ve yeni bulgu alarmı |

## 3. Donanım, arayüz, güvenlik ve operasyon

| İstek / yetenek | Bugünkü doğrulanabilir durum | Kabul ölçütü / açık iş |
|---|---|---|
| Tarayıcıdan internet, sitelerle etkileşim | **KISMİ:** dışarıdan tarayıcı otomasyonuyla CANO test edildi; CANO kendi içinden genel tarayıcı aracı çalıştırmıyor | Sahip izinli, sınırlı browser tool, site güvenlik kapsamı ve denetim |
| Windows bilgisayar / PowerShell / VS Code / RTX 3060 | **KISMİ:** yerel ortam mevcut; bu bulut oturumunda Windows kontrolü doğrulanmadı | Cihazdan açık bağlantı, denetimli yerel komut ve log |
| ChatGPT/Codex/GitHub/Render/Notion tek ekip | **KISMİ:** GitHub commit/PR/CI, Render deploy ve Notion kayıtları yapılabiliyor | Aynı görev ID'si ile uçtan uca senkron, rollout, readback, alarm |
| Otomasyonların kesintisiz ve denetlenebilir çalışması | **KISMİ:** CANO saatlik ve dört araştırma otomasyonu etkin; toplam sınır 5 | Her koşunun receipt/başarı/başarısızlık kaydı; aynı işi tekrar etmeme |
| Sesli/çok kipli arayüz, görsel/3D üretim | **AÇIK/KISMİ:** ChatGPT araçları ve masaüstü CAD uygulamaları ayrı | CANO uygulamasında gerçek giriş/çıkış entegrasyonu ve deney testi |
| Dijital organizmalar, koloni, evrim | **SİMÜLASYON:** digital_organism.py yerel ve izin kontrollü; gerçek canlı değildir | Sayısal simülasyon, kaynak sınırı, mutasyon/evrim ölçümü |
| Hücresel/lab araştırması, biyomimetik malzeme | **ARAŞTIRMA:** mevcut konular; fiziksel laboratuvar işletimi doğrulanmadı | Önce hesaplamalı model, deney tekrarı ve güvenlik denetimi |
| Fiziksel robot/işçi kolları, makineler, gövde üretimi | **AÇIK:** CAD/Blender/Bambu araçları kullanıcı cihazında; gerçekten üretilmiş robot veya özerk işçi doğrulanmadı | Tasarım, sanal test, güvenlik, fiziksel üretim, kullanıcı cihaz bağlantısı |
| Yetkisiz kopyalanmayan, izole ve dayanıklı ağ | **KISMİ:** agent quota, explicit approval, yerel lease, bazı giriş kuralları | Auth/izin, imzalı komut, bütçe, ağ ayrımı, saldırı/arıza testi |
| Çevrimiçi yedek/DR, depolama son tarihi | **RİSK:** ücretsiz Render PostgreSQL 2026-12-02 sona erme planı | Önce gerçek yedek ve geri okuma; sonra ücretsiz güvenli göç ya da bilinçli yükseltme |
| Sınırsız ölçek, dünyanın her yerinde çoğalma | **VİZYON, çalışan özellik değil:** fiziksel/sayısal kaynak sınırları mevcut | Yalnızca izinli sahipli cihazlarda kota ve kapatma mekanizması ile ölçekleme |
| Ücretsiz araçlar öncelikli, ücretliye onay, sırlar asla loglanmasın | **KISIT:** her geliştirme aşamasında geçerli | Tahmini ve fiili bütçe, provider limitleri, sıfır gizli anahtar sızıntısı |

## Önceliklendirilmiş uygulama dizisi

1. **Şimdi:** Plan→araştırma→eleştiri→sentez iş akışına kullanıcının açık izniyle sabit Crossref API üzerinden DOI **kaynak adaylarını** kat, kaynakları doğrulanmış ilan etme. Her adayın kaynağını, sınırını ve işlem durumunu görev checkpoint'ine yaz; test et, PR/CI/Render ile doğrula.
2. **P0:** Kalıcı kimlik + owner PostgreSQL (veri silmeden) → yedek/geri yükleme tatbikatı → bedelsiz sürdürülebilirlik kararı, özellikle **2 Aralık 2026** riski.
3. **P0:** Mevcut izinli PostgreSQL kuyruğunu canlı hesapta dedup, iki işçi, bütçe ve kesinti senaryolarıyla doğrula; çok aşamalı görev devamını ve genel yürütücü ihtiyacını ayrı izle.
4. **P1:** Gerçek birincil kaynak tam metin inceleme, claim-level doğruluk, bilimsel veri ve karşı kanıt; otomatik kaynak gösterme yalnızca açık eşleştirme varsa.
5. **P1:** Ajan öğrenme A/B kıyası + görev kalite skoru, geçmiş başarı ve başarısızlıkların analizi.
6. **P1:** Mevcut PostgreSQL Ana Kraliçe primitive’ini gerçek işçi transaction’larına bağla; güvenli yedek lider, split-brain, kesinti ve kurtarmayı canlıda doğrula.
7. **P1:** Notion/GitHub/Codex/Render görev kimliği zinciri, yayın sonrası browser smoke ve başarısız deploy geri alma.
8. **P2:** Yerel Windows/Ollama, tarayıcı ve donanım deney araçları kullanıcı tarafından bağlanınca gerçek entegrasyon.
9. **P2:** Dijital organizmalar/robotik simülasyon/çok düğümlü ölçek: fizik testi, kaynak kotası, onay, kapanış/geri alma; biyolojik veya fiziksel çıktıyı simülasyonla karıştırma.

## Bitirme kapısı

Bir özellik ancak **kod + platformlar arası ilgili test + canlı ortamda açık test + kalıcılık/kaynak doğrulaması gerektiğinde gerçek tatbikat + Notion/GitHub kayıt geri okuma** sağlandığında “tamamlandı” olur. Yalnızca PR/CI veya model yanıtı üretim doğruluğu değildir. API anahtarları arşivlenmez; başka kişilere/cihazlara izinsiz yayılım yapılmaz. Kullanıcı ödeme onayı olmadan ücretli kaynak başlatılmaz.


## Organism Lab — 4 Kasım 2026 güvenilirlik denetimi (geliştirme dalı)

- Kaynak dal: `feature/organism-lab-20261101`. GitHub branch comparison at audit: `ahead_by=106, behind_by=339`; main sürümüne otomatik birleştirme **yapılmadı**. Çalışan üretim uygulaması ile izole laboratuvar farklı kabul kapılarıdır.
- Doğrulanmış önceki laboratuvar kanıtları: CI #195 (Python 3.11/3.12), Core #559 (Windows/Ubuntu), Public research #300; kaydedilen JSON/CSV/SQLite'nin yeniden okunması ve karşılaştırma deneyleri, checkpoint'in 35→120. adım ileri oynatılması, altı ZIP'in kalıcı Library klasöründe doğrulanması. Notion ana laboratuvar kaydı: https://app.notion.com/p/40d2bd61682a81ee8745c28af627d98b.
- Yeni denetimde bulunan açık güvenlik hatası: farklı süreçlerin aynı dijital genom checkpoint dosyasına eşzamanlı yazması; kilitleme olmadan son yazan daha eski bir adımla veriyi geriye çevirebilir. Düzeltme kodu ve yarış koşulu testleri `bd7202c64cb8ac39f65396e791bb22fe2193b819` commit'ine kadar feature dalına yazıldı; `organism_lab/genome_checkpoint.py` artık Windows/Linux dosya kilidi kullanarak init/read/replay/replace işlemini koruyor. **Bu değişiklik için CI sonucu bekleniyorsa KODU DOĞRULANMIŞ SAYMA.** Takip: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/41879014652.
- P0 birleşme kapısı: Feature dalının `main` ile güncel farklılıklarını ve canlı CANO API/arayüz bağımlılıklarını kod incelemesiyle çöz; önce aynı dalda test, sonra temiz entegrasyon PR'ı, yeniden CI, yayın ve tarayıcı smoke, kayıt geri okuma/geri alma tatbikatı. Üretimi yanlışlıkla bozmamak için bu dokümantasyon güncellemesi dağıtım başlatmaz.
- Diğer **açık** başlıklar: kalıcı kimlik ve uzak PostgreSQL disaster-recovery/yeniden başlatma tatbikatı, genel CANO otomatik görev yürütücüsü (transactional kuyruk kodu artık mevcut), ikinci bağımsız ajan failover, gerçek kaynak bazlı doğruluk, fiziksel robot ve biyolojik laboratuvar. Her biri ayrı kanıt ister.


## 5 Kasım 2026 — kod ile envanter uzlaştırması

**İncelenen temel commit:** `03b51dc`. Bu bölüm dosya ve çağrı bağlantısı incelemesidir; yeni canlı test, başarılı CI koşusu veya dağıtım beyanı değildir. Yukarıdaki 4 Kasım laboratuvar dal farkları ve geçmiş test sayıları tarihsel kayıttır; bugünkü dal/üretim durumuna taşınmaz.

- **Kuyruk uygulamaya bağlı:** `app.py`, `core/authorized_queue_panel.py` ve `core/postgres_authorized_queue.py` imzalı owner için PostgreSQL kuyruğunu açar. Tekil anahtar, transactional claim, sınırlı retry, olay günlüğü ve `review_pending` taslak kaydı vardır. Süresi dolan lease manuel incelemeye engellenir. Kullanıcı tetiklemesi bir `answer(goal)` çağrısı yapar; arka plan scheduler, DAG/öncelik/deadline çözümü veya otomatik kabul yoktur. Deneme sayısı parasal maliyet ölçümü değildir.
- **Kraliçe uygulamaya bağlı değil:** `core/postgres_leader_lease.py` kayıtlı düğüm doğrulaması, DB saati, artan epoch ve aynı yazma transaction’ında `assert_fence` sunar. Kullanımı testler ve `scripts/check_cano_pg_queen_lease.py` ile sınırlıdır; üretim kuyruk/işçi yazımları bunu çağırmaz. `.github/workflows/cano-queen-lease.yml` sentetik PostgreSQL test tanımıdır.
- **Öğrenme hafızası ve ölçüm ayrı:** `core/agent_colony.py` kabul edilmiş dersleri prompt’a ekler; `evaluate_learning` farklı kanıt metinlerini sayar, model ağırlıklarını eğitmez. `core/benchmark_harness.py` bellekli/belleksiz eşleştirilmiş kıyas sunar (en çok 10 vaka / 40 model çağrısı). Harness varlığı veya ders sayısı, gerçek görev doğruluğunun iyileştiği anlamına gelmez; taze ölçüm raporu gerekir.
- **Kaynak okuma ve sınırlı karşılaştırma bağlı:** `core/collaborative_mission.py` ve `core/europepmc_evidence.py` DOI için Europe PMC metin/özet alabilir; komuta merkezinde kaynak okuma düğmesi vardır. `core/claim_evidence.py` birebir alıntı kontrolü, `core/claim_evidence_comparison.py` sözcük örtüşmesi ve açık olumsuzluk kontrolü yapar; ikincisi `core/colony_panel.py` arayüzündedir. Bu kapılar iddianın bilimsel doğruluğunu doğrulamaz; `claim_verified=False` korunur.
- **Ollama kısmen bağlı:** `app.py` model keşfi ve chat çağrısını, `core/cli.py` yerel araştırmayı Ollama’ya bağlar. Komuta merkezi, koloni ve kuyruk sağlayıcı callback’leri Groq’a bağlıdır. `core/research_orchestrator.py` ayrı üç rol geçişi kullanır ve webde yalnızca arama snippet’lerini inceler; uygulamadaki tüm checkpoint/kaynak kapılarını devralmaz. OpenCode/Kody/Codex genel görev devri bu kodla doğrulanmış değildir.
- **Saatlik koloni döngüsü çıkarım çalıştırmaz:** `.github/workflows/cano-colony-cycle.yml`, `scripts/cano_colony_cycle.py` ile SQLite öneri/audit durumunu ilerletir. Kayıtta `mode=proposal_only`; LLM çağrısı, deployment veya aktif ajan başlatma yoktur. GitHub runner dosyası canlı uygulama owner veritabanıyla aynı durum değildir.
- **CI tanımı ile sonuç ayrılır:** `.github/workflows/postgres-adapter-tests.yml` disposable PostgreSQL 17/18 üzerinde kuyruk, iki işçi, cockpit autosave/restore ve yedek/geri yükleme kontrollerini tanımlar. `.github/workflows/organism-lab.yml` ayrı laboratuvar test/deney hattıdır. Bunların tanımlanmış olması, en son committe geçtiğini veya üretimde aynı akışın doğrulandığını göstermez. Kabul kaydında koşu URL’si, SHA, canlı SHA ve readback ayrıca belirtilmelidir.

**Kalan teslim kapısı:** Kullanıcının tek giriş noktasından gerçek görev vermesi → aşama/sonuç kaydı → yenileme/yeniden başlatma sonrası devam → yedekten izole geri yükleme → hata halinde açık durum ve kanıt bağlantısı. Ayrı laboratuvar/CLI/CI parçaları bu uçtan uca akışın yerine geçmez.
