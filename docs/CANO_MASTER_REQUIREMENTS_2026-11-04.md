# CANO ana özellik / gereksinim envanteri — 4 Kasım 2026

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
| Kimliği belirli, idempotent kuyruk; tekrar deneme; işçi bütçesi | **AÇIK:** görev defteri var; paylaşılan otomatik yürütücü yok | Transactional kuyruk, değişiklik günlüğü, kontrollü retry/dedup, test |
| Görev alt parçalama / DAG / öncelik / süre / bağımlılık | **KISMİ:** araştırma planlayıcı rolü ve görev listesi | Bağımlılık çözme ve aşama sonuçlarına dayalı yürütme |
| Hata ayıklayan onarımcı ajanlar | **KISMİ:** test, kayıt, rol ve hata kurtarma var | Hata sınıflaması→minimal PR→CI→geri alma→kanıtlı dağıtım döngüsü |
| İkinci bağımsız ajan / Ana Kraliçe | **KOD/CI:** local SQLite fenced lease primitive; gerçek çoklu sunucu koordinasyonu yok | PostgreSQL transactional epoch fencing, kimlik doğrulama, split-brain ve failover testi |
| Çoklu LLM ve yerel Ollama / OpenCode / Kody / Codex orkestrasyonu | **KISMİ:** Groq ve Google seçimi; masaüstü Ollama/OpenCode ayrı kurulmuş | Gerçek, izinli, uçtan uca görev devri; yerel istemci bağlıyken doğrulama |
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
| Kaynakları otomatik kanıtla karşılaştırma | **AÇIK:** Crossref DOI metadata yalnızca aday; hakem/çıktı kaynak doğrulaması değildir | Birincil belge retrieval, iddia-bağlam eşlemesi, açık belirsizlik |
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
3. **P0:** İzinli, idempotent iş kuyruğu + maliyet/çağrı bütçesi + denetlenebilir event journal; tek komutla devam edebilme.
4. **P1:** Gerçek birincil kaynak tam metin inceleme, claim-level doğruluk, bilimsel veri ve karşı kanıt; otomatik kaynak gösterme yalnızca açık eşleştirme varsa.
5. **P1:** Ajan öğrenme A/B kıyası + görev kalite skoru, geçmiş başarı ve başarısızlıkların analizi.
6. **P1:** Ana Kraliçe: merkezi transaction epoch fencing + güvenli yedek lider; sahte split-brain, kesinti, kurtarma testleri.
7. **P1:** Notion/GitHub/Codex/Render görev kimliği zinciri, yayın sonrası browser smoke ve başarısız deploy geri alma.
8. **P2:** Yerel Windows/Ollama, tarayıcı ve donanım deney araçları kullanıcı tarafından bağlanınca gerçek entegrasyon.
9. **P2:** Dijital organizmalar/robotik simülasyon/çok düğümlü ölçek: fizik testi, kaynak kotası, onay, kapanış/geri alma; biyolojik veya fiziksel çıktıyı simülasyonla karıştırma.

## Bitirme kapısı

Bir özellik ancak **kod + platformlar arası ilgili test + canlı ortamda açık test + kalıcılık/kaynak doğrulaması gerektiğinde gerçek tatbikat + Notion/GitHub kayıt geri okuma** sağlandığında “tamamlandı” olur. Yalnızca PR/CI veya model yanıtı üretim doğruluğu değildir. API anahtarları arşivlenmez; başka kişilere/cihazlara izinsiz yayılım yapılmaz. Kullanıcı ödeme onayı olmadan ücretli kaynak başlatılmaz.
