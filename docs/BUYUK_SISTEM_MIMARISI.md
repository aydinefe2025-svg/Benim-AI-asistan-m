# Büyük Sistem — İlk Çalışan Çekirdek

## Niyet
Araştırma, üretim ve doğrulamayı tek görev akışında toplamak. Sistem hiçbir görevi sadece metin yazıldığı için tamamlandı saymaz. Doğrulama durumu, somut kanıt gerektirir.

## İlk modüller
- `core/task_store.py`: SQLite görev defteri, durum geçmişi ve kanıt zorunluluğu.
- `core/knowledge_store.py`: kaynak kayıtları, SHA-256 özeti ve kaynak bağlantılı iddialar.
- `core/ollama_client.py`: yerel Ollama API'si için standart kütüphane tabanlı istemci.
- `core/research_orchestrator.py`: planlayıcı → şüpheci denetçi → sentezleyici rol geçişi; görev kaydı ve Markdown raporu.
- `core/cli.py`: görev, kaynak, iddia ve yerel araştırma komut satırı arayüzü.
- `research_dashboard.py`: görev, kaynak, iddialar ve yerel Ollama araştırmasını yöneten Streamlit arayüzü.
- `tests/`: görev, kaynak, iddia, CLI, Ollama istemcisi ve araştırma iş akışı testleri.

## Yerelde çalıştırma
Proje kökünde PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dashboard.txt
python -m unittest discover -s tests -v
streamlit run research_dashboard.py
```

Varsayılan SQLite dosyası `data/research_system.sqlite3` olur. Farklı bir yol için `BUYUK_SISTEM_DB` ortam değişkeni verilebilir. Dashboard yerel bilgisayarda çalışır; internetten kaynak çekme veya yerel bilgisayara uzaktan erişim bu ilk sürümde otomatik değildir.

## Yerel Ollama araştırma komutu

Ollama'nın çalışır durumda olması ve modelin kurulu olması gerekir. Varsayılan model `qwen3:8b`:

```powershell
python -m core.cli --db data/research.sqlite3 research-run "Cezeri mekanizmalarının tarihsel etkisi"
```

Farklı endpoint/model için `--ollama-url` ve `--model` kullanılabilir. Çıktı varsayılan olarak `reports/` altına kaydedilir. Komut önce Ollama'daki kurulu modelleri kontrol eder.

**Sınır:** Üç rol aynı modeli kullanıyorsa bu bağımsız çoklu-model doğrulaması değildir. Bu akış web araması yapmaz; kaynak bulduğunu veya bilimsel sonucu doğruladığını iddia etmez. Rapor ve görev kaydı, dış kaynak doğrulaması yapılana kadar `done` durumunda kalır.

## Durum sözlüğü
- `planned`: planlandı, çalıştırıldığı iddia edilmez.
- `running`: çalışıyor.
- `blocked`: açık bir engel var.
- `done`: işlem yapıldı, bağımsız doğrulama tamamlanmamış olabilir.
- `verified`: somut test/kanıt kaydı eklendi.

## Güvenlik ve dürüstlük
- API anahtarları repoya yazılmaz; yerel secrets veya ortam değişkenleri kullanılır.
- Mevcut `app.py` ilk adımda değiştirilmez; yeni modüller izole olarak eklenir.
- Harici servisler, kota ve ağ erişimi olmadan çalışıyor kabul edilmez.
- Araştırma sonuçları, kaynağı ve yöntem sınırları belirtilmeden kesin bilgi diye yayımlanmaz.
- Kaynak kaydı, kaynağın doğrulandığı anlamına gelmez; iddiaların bağımsız incelemesi ayrı aşamadır.

## Bilinen barındırma engeli
Vercel'in bağlı projesi `app.py` dosyasını Streamlit scripti olarak buluyor ancak Python function giriş noktası (`app`, `application` veya `handler`) bulamadığı için build başarısız oluyor. Projede model API environment variable kayıtları da görünmedi; bağlı Supabase/Neon proje listeleri boş. Bu yüzden bu modüller şu an yerel çalışma çekirdeği olarak belgeleniyor; çalışan hosted AI uygulaması veya kalıcı hosted veritabanı olarak sunulmuyor.

## Sonraki katmanlar
1. Gerçek web arama/kaynak adaptörü ve kaynak metnini arşivleme.
2. GitHub/Notion adaptörleri ve güvenli yetkilendirme modeli.
3. Bağımsız denetim ajanı ve tekrarlanabilir hesaplama.
4. Uygun kalıcı veritabanı ve gerçek barındırma mimarisi.
5. Mevcut asistan arayüzüyle güvenli entegrasyon.
6. Bir araştırma vakasında uçtan uca doğrulama.
