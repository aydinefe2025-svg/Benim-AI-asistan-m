# Büyük Sistem — İlk Çalışan Çekirdek

## Niyet
Araştırma, üretim ve doğrulamayı tek görev akışında toplamak. Sistem hiçbir görevi sadece metin yazıldığı için tamamlandı saymaz. Doğrulama durumu, somut kanıt gerektirir.

## İlk modül
`core/task_store.py` standart Python kitaplığıyla SQLite tabanlı görev kaydı sağlar:
- görev oluşturma, listeleme ve durum geçişleri
- her durum değişimi için olay geçmişi
- kaynak/test çıktısı olarak kanıt listesi
- engel kaydı
- kanıt olmadan `verified` durumuna geçişi engelleme

## Planlanan katmanlar
1. Görev yöneticisi: hedefi alt görevlere ayırma ve durum takibi.
2. Kaynak toplayıcılar: web, GitHub, Notion ve yerel dosyalar için ayrı adaptörler.
3. Bilgi kasası: kaynak kimliği, URL, tarih, dosya hash'i, etiket ve konu bağlantıları.
4. Hesaplama: yerel Python/VS Code/Ollama; gerektiğinde ayrı bulut hesaplama.
5. Bağımsız denetçi: kaynak/iddia eşlemesi, yeniden hesaplama, testler ve belirsizlik raporu.
6. Arayüz: mevcut Streamlit uygulamasına görev panosu ve kanıt görünümü.
7. Otomasyon: yalnızca küçük testlerle doğrulanmış akışlar.

## Durum sözlüğü
- `planned`: planlandı, çalıştırıldığı iddia edilmez.
- `running`: çalışıyor.
- `blocked`: açık bir engel var.
- `done`: işlem yapıldı, bağımsız doğrulama tamamlanmamış olabilir.
- `verified`: somut test/kanıt kaydı eklendi.

## Güvenlik ve dürüstlük
- API anahtarları repoya yazılmaz; yerel secrets veya ortam değişkenleri kullanılır.
- Mevcut `app.py` ilk adımda değiştirilmez; yeni modül izole olarak eklenir.
- Harici servisler, kota ve ağ erişimi olmadan çalışıyor kabul edilmez.
- Araştırma sonuçları, kaynağı ve yöntem sınırları belirtilmeden kesin bilgi diye yayımlanmaz.

## Yerelde çalıştırma
Proje kökünde:

```powershell
python -m unittest discover -s tests -v
```

İlk testler SQLite görev kaydı ve kanıt zorunluluğunu kontrol eder. Testleri bu GitHub çalışma ortamında değil, kullanıcının bilgisayarında gerçekten çalıştırmak ayrıca gereklidir.
