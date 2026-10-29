# Büyük Sistem — İlk Çalışan Çekirdek

## Niyet
Araştırma, üretim ve doğrulamayı tek görev akışında toplamak. Sistem hiçbir görevi sadece metin yazıldığı için tamamlandı saymaz. Doğrulama durumu, somut kanıt gerektirir.

## İlk modüller
- `core/task_store.py`: SQLite görev defteri, durum geçmişi ve kanıt zorunluluğu.
- `core/knowledge_store.py`: kaynak kayıtları, SHA-256 özeti ve kaynak bağlantılı iddialar.
- `core/cli.py`: görev ve araştırma kayıtları için yerel komut satırı arayüzü.
- `research_dashboard.py`: görev, kaynak ve iddiaları görüntülemek/yönetmek için yerel Streamlit arayüzü.
- `tests/`: görev, kaynak, iddia ve CLI testleri.

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

## Planlanan sonraki katmanlar
1. Kaynak adaptörleri (web, GitHub, Notion, yerel dosyalar).
2. Araştırma planlayıcısı ve görev bağımlılıkları.
3. Bağımsız denetim ajanı ve tekrar üretilebilir hesaplama.
4. Yerel Ollama adaptörü ve kontrollü kod çalıştırma.
5. Mevcut asistan arayüzüyle güvenli entegrasyon.
6. Gerçek araştırma vakasında uçtan uca doğrulama.
