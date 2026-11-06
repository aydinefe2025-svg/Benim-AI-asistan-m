# CANO – VO-MASD-Hier kontrollü hiyerarşi denetimi (6 Kasım 2026)

**Yeni hedef:** Önceki 32 `forward_codebook` eşdeğerlik denemesinden ileri giderek, `forward_code` çağrısı içinde alt beceri gösterimleri → gruplama → TopSkillEncoder (attention) → üst/alt ayrık beceri kitapları → birleşik latent → gradyan hesaplarını aynı CPU koşusunda yürütmek.

## Özgün kaynak ve deney sınırı

- Makale: [Variational Offline Multi-agent Skill Discovery, IJCAI 2025](https://doi.org/10.24963/ijcai.2025/538).
- Kaynak: [LucasCJYSDL/VOMASD](https://github.com/LucasCJYSDL/VOMASD) (MIT; telif © 2024 Jiayu Chen), pinned commit `ff05a1f2bebd1ed8c1a49afc424bac8905eb4de3`.
- Pinned upstream blob dosyaları: `vomasd_hier_policy.py`: `621980122d13f1c8dab31c4ccabe9f5c4099c95f`; `vomasd_module.py`: `f94834f63dded1b34b8b566d6449004c0fb2982c`; `transformer.py`: `8e0e4222597a6fa0f2295144066a811f99588e15`.
- Özgün `forward_codebook` fonksiyonu 1.232 bayt, SHA-256 `1e98587e760bda07dd0c08699fa912cbc4adab115decb483f048f1fca263c680`; kaynak bozulma kontrolü çalışıyor.
- Yeni `native_hierarchy.py`: upstream `forward_code` **kaynakla eşdeğer işlemlerinin yorumlardan arındırılmış, bağımlılıkları izole edilmiş aktarımı**. Orijinal metnin byte-identical kopyası değildir. `original_top_skill_components.py` kaynakla eşdeğer `TopSkillEncoder`, `LightEncodeBlock`, `SelfAttention` içerir.
- `FixtureGrouper` **özgün öğrenilmiş Grouper DEĞİL**, sabit ve doğrulanmış bir grup düzeni sağlayan test düzeneğidir. **SC2/SMAC, öğrenilmiş grup belirleme, çevrimiçi reinforcement learning, yayın win-rate metrikleri ve makalenin tam replikasyonu ÇALIŞTIRILMADI.**
- Eski orijinal eğitim betiği yalnızca veri olarak tutulur. `algo=odis` varsayılanı, 8 milyon adım ve GPU seçimi nedeniyle yürütülmez.

## Yürütülen deney ve bulgu

- PyTorch CPU, boyutlar `B=2`, `T=3`, `A=3` ajan, gizil beceri `D=4` (birleştirilmiş `D=8`), eğitim/girdi **sentetik**.
- 16 yeni tam-ileri-geçiş regresyonu + 6 yeni hassasiyet testi + 3 CLI testi; önceki 20 test korunmuştur. Toplam **45/45** unittest başarılı (`ResourceWarning` hata sayılarak).
- 16 ayrı seed ile üst/alt kayıp, şekil, gradyan ve NaN/inf testleri; tümü sonlu, gradyanlar model parametrelerine ve alt beceri girdilerine ulaşıyor.
- 32 seed × 4 sabit grup düzeni = **128 kontrollü durum**. Başlangıç ağırlıklarında tüm tohumlarda kuantize birleşik çıkışlar grup düzeninden bağımsız; üst kod kullanımının medyanı **1/7**. TopSkillEncoder'ın gruba bağlı sürekli aktivasyonunda küçük ama sıfır olmayan farklar görülüyor (en yüksek ≈ `4.74×10⁻⁶`). Baş ağırlıkları kontrollü olarak 10.000 kez büyütülen pozitif kontrolde çıktı gruba bağlı değişiyor: **farklılaşmanın matematiksel olarak mümkün olduğu** görülüyor. Bu müdahale eğitim ya da makale performansı değildir.
- Önemli ara şekil kuralı: gerçek Grouper'ın beceri çıktısı `(B*T, A, D)` olarak düzleştirilir. İlk fixture `(B,T,A,D)` döndürünce upstream işlemin `emb_rwd` toplaması şekil uyuşmazlığı verdi; fixture gerçek sözleşmeye göre düzeltildi, test eklendi.

## Bağımsız çalıştırma

```bash
cd src
python -W error::ResourceWarning -m unittest -q test_vomasd_cpu test_native_parity test_hierarchical_forward test_group_sensitivity test_experiment_cli
python run_hierarchy_experiment.py --output ../evidence/hierarchy_experiment.json
```

İkinci komut eski raporu tek bir atomik JSON değiştirmesiyle günceller. `hierarchy_experiment.json` deneme bazında sonuçları ve bilimsel sınırlama bayraklarını içerir. GitHub CI dosyası `.github/workflows/cano-vomasd-hierarchy-smoke.yml`, normal PR/ana dal testi olarak aynı denemeyi yapar. **GitHub CI'nın bağımsız sonucunu görmeden tamamlandı iddiası verilmez.**

## Sonraki bilimsel iş

Gerçek SMAC/StarCraft kurulumu, yasal erişilebilir özgün veri/checkpoint, aynı seed ve map üzerinde tam VO-MASD ile ODIS'in tarafsız karşılaştırması; ham win-rate günlükleri ve kaynak kontrolü. Bunun için ayrı, yeterli işlem gücü olan ortam gerekir; mevcut küçük CPU testi bunun yerine geçmez.
