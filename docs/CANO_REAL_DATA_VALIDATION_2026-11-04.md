# CANO gerçek veri araştırma döngüsü — 2026-11-04

## Çalıştırılmış doğrulama (yerel)

Önceki Keşif Ağı v1.8 paketi temel alınarak gerçek veriyle çalışan `cano_real_cycle.py` eklendi. Çalışma paketi ve raporları ChatGPT Dosya Kütüphanesi'nde:

`/Ortak Kesif Ekosistemi/CANO_Real_Data_2026-11-04/`

- `CANO_Research_Cycle_2026-11-04.zip`: 56 dosya, 509100 bayt.
- `RESULTS.md`: gerçek veri deney raporu.
- `validation_run.json`: denetim çıktısı.

Arşiv SHA-256: `105b288682da9f9e4a58e7b8b105579db4c6db7f0c1f529e40adc98fc2f57372`

## Gerçek veri ve hesaplama

| Kaynak | Kayıt | Özellik | Çoğunluk tabanı | 5-kat CV model doğruluğu |
|---|---:|---:|---:|---:|
| UCI Wine kimyasal ölçümler | 178 | 13 | %39,90 | %98,33 |
| sklearn Digits el yazısı görüntüleri | 1797 | 64 | %10,13 | %97,11 |

İki veri kümesi de scikit-learn dağıtımıyla birlikte gelir; ağdan yeni veri indirilmedi. Her deney: `StratifiedKFold(n_splits=5,shuffle=True,random_state=42)`, eğitim katına özel `StandardScaler`, `LogisticRegression(max_iter=1200)`. Karşılaştırma `DummyClassifier(strategy='most_frequent')`. Bu metodolojik doğrulama yeni bilimsel keşif değildir.

## Kayıt bütünlüğü

- 1975 gözlem + 2 deney özeti = 1977 atomik SQLite bulgu/makbuz kaydı.
- Makbuz denetimi: 1977/1977, `ok=true`.
- Aynı girdiyle tekrar çalıştırma: `inserted=0`, `already_processed=1977`.
- Son `unittest discover`: **135/135 test başarılı**.
- `ResourceWarning`: **0**. Önceden açık bırakılan bazı SQLite bağlamları kapatıldı.
- SHA-256 manifest ve paket ZIP bütünlüğü geçti. Tüm bulgular `pending_review` durumunda.

## Tekrar üretme

```sh
python -m pip install "numpy>=2,<3" "scikit-learn>=1.6,<2" "opencv-python>=4.9,<5"
python -m unittest discover -q
python cano_real_cycle.py run --output real_run
python cano_real_cycle.py verify --output real_run
python cano_real_cycle.py run --output real_run
```

Windows için `RUN_WINDOWS.cmd` pakette yer alır. Paket ChatGPT yerel çalışma ortamında test edilmiştir; kullanıcının bilgisayarına kurulmuş bir servis değildir.

## Kaynaklar

- Wine: https://doi.org/10.24432/C5PC7J
- Digits: https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_digits.html

## Bir sonraki entegrasyon işi

Bu kaydı gören Codex/diğer ajanlar, öncelikle ZIP içindeki kodu depoya taşıyıp mevcut test CI akışına bağlayabilir. Ardından kontrollü canlı veri kaynağı, günlük zamanlama, senkronizasyon hatası için tekrar deneme ve Notion ile GitHub'a uçtan uca doğrulanmış kayıt akışı eklenmelidir. Bunlar henüz tamamlandı olarak işaretlenmemelidir; gerçek kimlik bilgileri sır veya depoya commit edilmemelidir.
