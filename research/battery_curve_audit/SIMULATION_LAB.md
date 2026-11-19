# CANO Batarya — 1.300 koşuluk sanal laboratuvar

**Durum:** Tamamen sentetik, kod davranışını doğrulayan çevrimdışı araştırma. Gerçek cihaz, batarya hücresi veya müşteriye ait ölçüm yok. Deneme senaryoları bağımsız saha etiketleri değildir.

## Tek komut

```sh
python research/battery_curve_audit/battery_virtual_lab.py --trials 100 --seed 20261119 --output ./CANO_BATARYA_SANAL_LAB_1300.json
```

Python 3.12+ standart kütüphanesi yeterlidir. Çalışma, 13 senaryo ailesini 100 farklı deterministik tohumla üretir (toplam **1.300 dört hücreli sanal deney, 5.200 eğri**). Kaynak/yöntem kodu aynı repodaki `battery_virtual_lab.py`; kaynak veri dışarıdan okunmaz, ağ çağrısı yapılmaz. Aynı hedef dosya varsa üzerine yazılmaz.

## Deney tasarımı

Dört hücreli her deneyde monoton azalabilen gerilim profili (düzgün doğrusal, sinüzoidal ve son boşalma kıvrımı) yeniden sentezlenir. Profiller **gerçek elektrokimyasal model veya deney değil**, sayısal test vektörleridir. Deneyler:

1. Ayrı ve belirgin eğriler, 2. birebir kopya, 3. farklı sayı biçimiyle tam aynı eğri, 4. +1 mV kontrollü kopya, 5. farklı örnekleme ızgarası, 6. +3 saat sadece zaman kökeni kayması, 7. +3,5 mV sabit bias, 8. bağımsız tanımlanmış ama yakın iki eğri, 9. az sayıda ölçümlü eğri, 10. hemen hemen düz eğri, 11. yanlış voltaj birimi, 12. monoton olmayan zaman, 13. yalnız bir bağlı gruba düşen dört kopya.

`decision` gerçek `customer_pipeline.audit_offline()` fonksiyonundan gelir. Yalnız toplamlar, beklenen ve gözlenen sonuçlar, sentetik grup bağlanması ve ortanca çalışma süreleri JSON'a yazılır. Örnek ham zaman-gerilim çiftleri rapora yazılmaz. `--include-trials` seçeneği yalnız sentetik ve kimliksiz deneme sonuçlarını ekler.

## Önceden tanımlı sentetik bulgular — `seed=20261119`, `100` tekrar/aile

| Ölçü | Eski sürüm (2 mV salt mutlak zaman) | Yeni sürüm (zaman-kökeni ek inceleme) |
|---|---:|---:|
| Kurgusal kopya senaryosu | 600 | 600 |
| İncelemeye giren | 400 | 500 |
| Kaçırılan | 200 | 100 |
| Yapay bağımsız iki senaryo ailesinde inceleme | 100 / 200 | 100 / 200 |
| Beklenen davranıştan sapma | 0 | 0 |

Yeni kaydırılmış-köken kontrolü, +3 saat ile kaydırılan **100/100** kontrollü kopyayı yakaladı ve aynı bağlı hücre grubuna yerleştirdi. +3,5 mV bias senaryosu **100/100** kaçırılmaya devam ediyor: gerilim offsetini körlemesine kaldırmak +1 mV farkla *bağımsız kaynak* olarak kurgulanmış eğriler dahil **200/200** sözde bağımsız kontrolü incelemeye gönderebilir. Bu nedenle bias silme yaklaşımı **ürün koduna eklenmedi**. Bu tablodan gerçek dünyanın FPR/FNR, sensitivity veya specificity oranları çıkarılamaz; senaryolar tasarımca dengeli seçilmiştir ve fiziksel gerçeklik dağılımını temsil etmez.

## Teknik karar

`near_duplicate_guard.relative_time_origin_candidates()` yalnız farklı ilk zaman kökenini sabitçe kaydırır. **İnterpolasyon eşiklerini, voltajları, veriye ait kimlik hashlerini değiştirmez.** Başlangıç farkı ilgili süreye göre en az %0,5, uç noktaları hizalı ve tüm özgün iç düğümlerde gerilim farkı en çok **2 mV** ise `RELATIVE_TIME_ORIGIN_REVIEW_ONLY` kaydı üretilir. Bu, bir *inceleme adayıdır*; aynı fiziksel numune, sahtecilik veya kopya kanıtı değildir. Gerekli grup atomik holdout hesabı, bu bağı da dikkate alır. Eşleşmeyen zaman esnemesi veya büyük voltaj biası **güvenli değildir; bağımsızlık garanti edilmez.**

## Test ve kabul

```sh
python -m unittest discover -s tests -p 'test_battery_time_origin_guard.py' -v
python -m unittest discover -s tests -p 'test_battery_virtual_lab.py' -v
python -m unittest discover -s tests -p 'test_battery_customer_pipeline.py' -v
```

Bu simülasyon gerçek müşteri izni, sahada cihaz kalibrasyonu, SOH tahmini, gerçek hata oranı, gelir/ödeme veya fiziksel üretim yetkisi yerine geçmez. Tüm işlemler ağ bağlantısı olmadan yerel çalışır. Bükreş Politeknik'in bağımsız yayımlanmış 20 CSV testi GitHub CI'da ayrıca korunur; kaynak veri CC BY 4.0 (BulyK47/battery-datasets, DOI 10.21227/cm0f-jg66).
