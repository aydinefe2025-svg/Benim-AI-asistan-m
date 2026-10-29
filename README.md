# Büyük Sistem — kişisel araştırma ve üretim çekirdeği

Bu depo, araştırma görevlerini, kaynak kayıtlarını, kanıt bağlantılarını ve yerel Ollama araştırma akışını bir araya getiren ilk çekirdektir. Tam otomatik genel zekâ, canlı web tarayıcı erişimi veya bağımsız çoklu-model uzlaşması iddiasında bulunmaz.

## Mevcut özellikler
- SQLite tabanlı kalıcı görev defteri ve durum geçmişi.
- Kaynak kayıtları, metin SHA-256 özeti ve iddialara destek/çelişki/context bağlantıları.
- Görev ve kaynakları yönetmek için komut satırı arayüzü.
- Yerel Ollama ile üç aşamalı araştırma taslağı: planlayıcı → şüpheci denetçi → sentezleyici.
- Streamlit kontrol paneli: görevler, kaynak kasası, iddialar ve yerel araştırma sekmesi.
- Kanıt olmadan `verified` durumuna geçişi engelleyen görev durumu kuralı.
- GitHub Actions üzerinde otomatik birim testleri.

## Yerel kullanım (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dashboard.txt
python -m unittest discover -s tests -v
streamlit run research_dashboard.py
```

Varsayılan SQLite veri dosyası `data/research_system.sqlite3` konumunda oluşturulur. `BUYUK_SISTEM_DB` ile başka yol seçilebilir.

## Komut satırından araştırma

Ollama'nın açık olması ve `qwen3:8b` modelinin kurulu olması gerekir:

```powershell
python -m core.cli --db data/research.sqlite3 research-run "Cezeri mekanizmalarının tarihsel etkisi"
```

Bu üç rolün tamamı aynı modeli kullanıyorsa bağımsız çoklu-model doğrulaması değildir. Akış web araması yapmaz; kaynakları ve sonuçları dışarıdan doğrulama görevi ayrıca yapılmalıdır. Rapor `reports/` altına yazılır, görev kaydı SQLite'a eklenir.

## Kaynak/iddia kayıtları

```powershell
python -m core.cli --db data/research.sqlite3 task-add "Makale iddialarını kontrol et"
python -m core.cli --db data/research.sqlite3 task-list
python -m core.cli --db data/research.sqlite3 source-add "https://example.org/paper" "Örnek makale"
```

Kaynak kaydı tek başına içeriğin doğrulandığı anlamına gelmez.

## Mimari ve envanter
- [İlk çekirdek mimarisi](docs/BUYUK_SISTEM_MIMARISI.md)
- [Bağlı sistem envanteri ve bilinen engeller](docs/SYSTEM_INVENTORY_2026-10-29.md)

## Barındırma durumu
Vercel projesi şu an hata veriyor: kökteki `app.py` Streamlit betiği ve Vercel Python runtime'ının beklediği `app`/`application`/`handler` nesnesini dışa aktarmıyor. Ayrıca Vercel ortam değişkeni envanteri boş; mevcut uygulamanın model anahtarları orada görünmüyor. Bu yüzden repo şu an test edilmiş bir çekirdek ve yerel arayüz olarak sunulur; çalışan hosted AI servisi olarak sunulmaz.

## Güvenlik
API anahtarlarını kaynak koda veya raporlara yazma. Harici ücret/kota gerektiren araçları otomatik etkinleştirme. Bir görev ancak test veya açık doğrulama kanıtı varsa `verified` sayılır.
