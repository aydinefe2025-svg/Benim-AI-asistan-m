# Bağlantı ve sistem doğrulaması — 2 Kasım 2026

## Kapsam ve kaynak

Açılan çalışma dizini boştu. Mevcut `aydinefe2025-svg/Benim-AI-asistan-m`
deposu geçmişiyle klonlandı; proje yeniden oluşturulmadı. Render'ın kullandığı
`fix/sqlite-backup-restore-20261031` dalının `8824269593b2fc0f08bbf446531151b6c21452a7`
commit'i temel alındı. `main` daha sınırlı bir uygulama içerdiğinden bu dal
otomatik olarak main'e birleştirilmedi. Değişiklik dalı:
`audit/connections-robotics-20261102`.

## Çalışan: ölçülmüş sınırlar içinde

| Bileşen | Gerçek kontrol | Sonuç ve sınırı |
|---|---|---|
| GitHub | Kimlik ve depo listeleme, geçmişiyle klonlama | Okuma başarılı; yazma sonucu PR'da ayrıca izlenir |
| Kody MCP | `search`, ardından `mcpServerList` salt okunur çalıştırma | Başarılı; Notion bağlantısı ready/connected, 68 araç keşfedilmiş. Bu araçların tek tek işlevleri test edilmedi |
| Ollama | Yerel `/api/version`, `/api/tags`, projenin `OllamaClient.chat` çağrısı | Sürüm 0.40.13; qwen3:8b mevcut; 30 saniye zaman aşımı sınırıyla boş olmayan yerel sohbet yanıtı alındı |
| OpenCode | Mevcut npm kurulumundan `--version` ve `models` | v2.2.3; model listesinde `ollama/qwen3:8b` mevcut. OpenCode üzerinden çıkarım çalıştırılmadı |
| Render | Workspace/servis/deploy listeleme; `/_stcore/health` GET | HTTP 200 `ok`; son deploy live ve temel commit ile eşleşiyor. Sağlık kontrolü AI sağlayıcılarını doğrulamaz |
| Çekirdek ve robot veri doğrulaması | Windows / Python 3.15 sanal ortamında unittest | 165 test başarılı; 0 hata/başarısızlık |
| Uygulama bağımlılıkları | Sanal ortama kurulum, gerçek import, `pip check` | Streamlit, requests, Groq, google-genai, Telegram ve dotenv importları başarılı; bağımlılık çatışması yok |
| Streamlit başlangıcı | Gerçek `streamlit.testing.v1.AppTest`, sağlayıcı anahtarları olmadan | İstisna yok; eksik anahtar uyarısı beklenen biçimde çıktı. Ücretli model çağrısı yapılmadı |

Kody çalıştırması 0 worker units bildirdi. Kaynak, anahtar veya kimlik doğrulama
değerleri bu rapora aktarılmadı.

## Başarısız kontroller ve düzeltme sonuçları

1. İlk unittest: 160 test, 2 başarısızlık, 74 hata. SQLite bağlam yöneticisi
   commit/rollback yapıyor fakat bağlantıyı kapatmıyordu. Windows dosya kilitleri
   geçici klasör temizliğini ve başarısız yedek işlemlerinin temizliğini bozuyordu.
2. KnowledgeStore ve manifest işlemleri kapanan, commit/rollback koruyan bağlantı
   bağlamına geçirildi. Yedek, taslak ve içe aktarma bağlantıları deterministik
   kapatılıyor. Testlerin kendi ham SQLite bağlantıları da kapatıldı.
   Ara sonuçlar: 164 test / 41 hata, sonra 164 test / 3 hata, sonra 164/164 başarılı.
3. Robot giriş testleri entegrasyon öncesinde 4 test / 6 başarısız alt durum ve
   5 hatayla açığı gösterdi. Yeni denetleyiciler boolean, kesirli, NaN/sonsuz,
   yanlış boyutlu, sınır dışı koordinatları ve geçersiz hareket dizilerini reddeder.
   JSON koordinat dizileri tuple'a normalize edilir. Mevcut `move_grid_robot`
   çağrı yoluna entegredir; hareketlerin tamamı simülasyondan önce denetlenir.
4. Bağlantı kapanması ve rollback regresyon testi eklendi. Son sonuç 165/165.
   GitHub Actions test matrisi Windows ve Linux olarak genişletildi; uzak CI
   sonuçları yerel sonuçlardan ayrı değerlendirilmelidir.
5. Başlangıç ortamında uygulama bağımlılıkları yoktu. Yalnızca bu kopyanın
   `.venv` ortamına kuruldu. Telegram/dotenv için `requirements-bot.txt` eklendi;
   bot ağı/polling başlatılmadı.
6. İlk GitHub/Render/PyPI doğrudan ağ denemeleri sandbox tarafından engellendi.
   İzin verilen dış ağ tekrarları başarılı oldu; bu servis kesintisi değildi.
7. OpenCode PATH'te yoktu; mevcut `%APPDATA%/npm/opencode.cmd` bulundu.
   Sandbox komut çalıştırmayı engelledi; izin verilen sürüm kontrolü başarılı.
   `models ollama` v2.2.3'te desteklenmiyor (exit 1); doğru `models` komutu
   exit 0 ile `ollama/qwen3:8b` dahil model listesini döndürdü.

Her aşamanın başarısız test adları ve sonuçları [test-results.json](test-results.json)
dosyasında; kurulu paket sürümleri [installed-packages.txt](installed-packages.txt)
dosyasında kayıtlıdır. `git diff --check` başarılıdır.

## Erişilemeyen veya henüz doğrulanmayan

- **OpenCode çıkarımı:** sürüm ve Ollama model kaydı doğrulandı; OpenCode
  içinden uçtan uca model yanıtı test edilmedi. Mevcut kurulum korundu.
- **Python 3.12:** launcher kayıtlı fakat mevcut sandbox bu yorumlayıcıyı
  başlatamadı. Yerel test kanıtı Python 3.15 içindir; Linux/3.12 CI sonucu ayrıdır.
- **Groq/Google ve Telegram canlı işlevleri:** yalnızca bağımlılık/import ve
  mevcut otomatik test kapsamı doğrulandı; canlı model/mesaj çağrıları yapılmadı.
- **Fiziksel robot, sensör telemetrisi ve MuJoCo:** yeni denetleyici mevcut grid
  simülasyonu kapsamındadır. Depodaki `research/mujoco-ci-issue-23` dalı görüldü;
  o daldaki fizik simülasyonları bu görevin kaynak dalına birleştirilmedi ve
  çalıştırılmadı. Fiziksel robot veya fizik motoru doğrulandı denemez.
- **Render kalıcılığı:** servis free planında; mevcut SQLite verilerinin kalıcı
  disk güvencesi bu denetimle kanıtlanmadı. Canlı veritabanına müdahale edilmedi.

## Yeniden çalıştırma

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m pip check
git diff --check
```

Mevcut veri dosyaları silinmedi. Canlı ortama dağıtım yapılmadı. Ücretli servis,
model indirme veya altyapı oluşturma başlatılmadı. Nötron yıldızı araştırma
dosyaları ve araştırma içerikleri değiştirilmedi.
