# CANO — gerçek veriyle doğrulanan çevrimdışı araştırma çekirdeği

Bu dizin, CANO'nun **çalıştırılabilir kaynak kodunu** ve birim testlerini içerir. İki scikit-learn veri kümesinin (UCI Wine: 178 örnek, Digits: 1797 örnek) 5 katlı çapraz doğrulaması yapılır. Gözlemlerle deney özetleri aynı SQLite veritabanında atomik bulgu/makbuz olarak tutulur ve SHA-256 dosya manifestiyle denetlenir. **Yeni bilimsel keşif, sürekli ajan veya canlı internet toplama iddiası yoktur.**

## Başlat

Python 3.12+ ve sanal ortam önerilir.

```bash
python -m pip install -r requirements.txt
python -W error::ResourceWarning -m unittest discover -q
python ci_smoke.py --output .local-run
python cano_real_cycle.py verify --output .local-run
```

Windows: `python ci_smoke.py --output .local-run` komutuyla aynı denetim yapılabilir. Çalışma alanına `.local-run/` veritabanı ve rapor dosyaları oluşturulur. Bulgu statüleri `pending_review` olarak kalır.

## CI ve günlük denetim

`.github/workflows/cano-real-research.yml` pull request'te testleri çalıştıracak ve hata halinde başarısız olacaktır. **Günlük zamanlama ancak bu iş akışı `main` dalına alındıktan ve GitHub Actions etkin olduğunda çalışır.** Çalışma çıktısında yalnız rapor ve manifest, GitHub Actions artifact olarak saklanır. Veri kümesi ZIP'i, kimlik bilgileri veya bulgu SQLite dosyası herkese açık artefakta gönderilmez.

## Sınırlar

- Veriler hazır `scikit-learn` kurulumundan gelir; çevrimiçi yeni kaynak keşfi yapılmaz.
- Digits için yazar bazlı bağımsız örnek ayrımı bilinmiyor; genel kullanım güvenilirliği kanıtlanmış değildir.
- Kullanıcı bilgisayarına veya Render'a kurulum yapmaz.
- Kaynak dosyaları değiştirilirse `verify` başarısız olur; manifest dijital imza yerine geçmez.
- GitHub Action'ın gerçek sunucu koşusu, bu dizin PR'da açıldıktan sonra ayrıca kontrol edilmelidir.

Önceki denetim geçmişi ve yerel tam çalışma paketi ana dosya kütüphanesinde `/Ortak Kesif Ekosistemi/CANO_Real_Data_2026-11-04` klasöründedir.