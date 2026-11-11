# CANO 'tohum' ve çevresel enerji çeşitliliği — model deneyi

**Tarih:** 2026-11-11  
**Ana iş:** `cano.core / one-seed-resilience / equal-energy-outage-and-founder-loss`  
**Kapsam:** Güvenli, kapalı, deterministik yazılım simülasyonu. Gerçek enerji hasadı, fiziksel robot, üretim ağında otomatik ajan veya yetkisiz kopyalama değildir.

## Hipotez
Tek tasarım tohumu, kendisinden türeyen birimler aracılığıyla kurucu kaybolduktan sonra yeniden büyümeye devam edebilir. Aynı toplam enerji varsayımı altında birbirini tamamlayan kaynaklardan gelen akış, kesintili tek bir kaynaktan gelen enerjiye göre daha az duraklama doğurabilir.

## Mevcut CANO ile ilişki
- `core/digital_organism.py`: finite/human-approved sanal çoğalma; gerçek enerji üretimi yok.
- `core/agent_colony.py`: kalıcı uzman kayıtları ve kabul edilmiş dersler; gerçek işçi süreçleri değil.
- Bu deney `core/seed_ecosystem.py` içindeki ayrı sanal enerji akışı, kurucu arızası, yavrudan yavruya çoğalma, kapasite sınırı ve kayıt geri okuma davranışını ölçer. Üretim kodunu/depolamasını değiştirmez.

## Yöntem ve kaynak kısıtları
8 deterministik tik, başlangıç 1 tohum, en çok 10 birim, depolama tavanı 12 varsayımsal enerji birimi, aktif adımda birim başına 1 enerji, yeni birim için 2 enerji. 4. tik öncesinde kurucu birim 1 bilinçli olarak silinir. Tek adımda en fazla 1 yeni birim. Tüm simülasyon adımları `authorized=True` ile tetiklenir. Ajanlar gerçek süreç değildir; kayıtlar enerji yetersizliğinde *dormant* kalır. Dış ağ, gizli anahtar ve gerçek donanım yoktur.

- **Güneş / düşük toplam:** her tik [4,4,4,0,0,0,4,4] → toplam 20 sanal enerji.
- **Güneş / eşit toplam:** her tik [9,9,9,0,0,0,9,8] → toplam 44 sanal enerji.
- **Çok kaynaklı / eşit toplam:** güneş [4,4,4,0,0,0,4,4], su her tik 2, ısı her tik 1 → toplam 44 sanal enerji.

Bu değerler watt, joule, verim, insan/gezegen enerjisi ölçümü değildir. Gerçek enerji kaynağına dönüşüm ve fiziksel enerji bütçesi ayrı mühendislik deneyleri gerektirir.

## Ölçülen bulgular

| Profil | Giriş | Duraklayan tik | Sondaki kayıt nüfusu | Toplam doğum | 4. tik kurucu kaybı sonrası en yüksek nesil | Depo taşması | Checkpoint geri okuma |
|---|---:|---:|---:|---:|---:|---:|---|
| Güneş, düşük toplam | 20 | 3 | 4 | 4 | 4 | 0 | PASS |
| Güneş, eşit toplam | 44 | 2 | 6 | 6 | 6 | 9 | PASS |
| Güneş+su+ısı, eşit toplam | 44 | 0 | 6 | 6 | 6 | 2 | PASS |

Ana kontrol: eşit toplam 44 enerji ile **2 yerine 0 dormant tik**. Farkı yalnızca 'fazladan enerji eklendi' açıklamasıyla geçiştirmek mümkün değildir; akış zamanlaması ve depo tavanı rol oynar. Bununla birlikte bu, yalnızca belirtilen sayısal senaryo için kanıttır, genel bir performans veya fiziksel verim kanunu değildir.

## Tekrar üretim

```bash
python -m unittest discover -s tests -p 'test_seed_ecosystem.py' -v
PYTHONPATH=. python scripts/cano_seed_lab_demo.py > demo_results.json
```

Yerel test: **10 / 10 PASS**, Python 3.13, `unittest` (standart kütüphane). İlk RED: `ModuleNotFoundError: core.seed_ecosystem`; uygulama eklendikten sonra GREEN. Üç senaryoda SHA-256 checksum'ı ile checkpoint kayıt/geri okuma eşleşti. SHA-256 kontrolü yalnızca kazara bozulmaya karşıdır; güvenilir imzalı yedek veya uzak veri kurtarma kanıtı değildir.

## Açıktaki mühendislik adımları
1. Gerçek enerji kaynağı ölçüleri (mW, Wh, görev profili) ve depolama verimiyle model kalibrasyonu.
2. Fiziksel düğüm çalışma bütçesi ile dijital ajan iş bütçesini ayrı tutup birleştirme.
3. Var olan gerçek CANO uzman/kuyruk sistemiyle yalnızca test ortamında kontrollü adaptör; kimlik doğrulama, limit, maliyet ve durdurma kapıları.
4. GitHub CI Windows/Linux testi, bağımsız kod incelemesi, Notion ana kütüphane bağlantısı ve gerçek arşiv geri okuma.
5. Ana düğüm ve kayıt deposu tamamen kaybolunca harici, doğrulanmış kurtarma tohumu. **Bu deneyde tamamen yok olan nüfus kendiliğinden dirilmiyor.**

**Sonuç etiketi:** `local_test_passed`; production/live self-reproduction **NOT VERIFIED**. Ücret/cihaz/üçüncü taraf erişimi yok.
