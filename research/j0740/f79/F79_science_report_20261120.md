# A01.01.51 — F79: özgün EOS (P, ε, H) verisinin enterpolasyon-bağımsız soğuk nedensellik zorunluluğu

**20 Kasım 2026 — Yeni fiziksel gerek-şart analizi.** Bu çalışmada F73'ün BPS–F67 MPA1 faz eşleme testi tekrarlanmadı. F75–F78'in önceden üretilmiş yıldızları ve yedi orijinal EOS kaynak dosyaları byte-kilitli ve salt okunur kullanıldı. Yeni RNS yıldızı, orijinal NICER/XMM 12,9 GB foton olayı, X-PSI, posterior veya fiziksel EOS onarımı oluşturulmadı.

## Özgün bulgu ve matematiksel ispat

Soğuk, tek-değerli, türevlenebilir ve nedensel barotrop için geometrik birimlerde `0<dP/dε≤1`, dolayısıyla `dε/dP≥1`. Bir özgün veri aralığında başlangıç `(P0, ε0, H0)`, bitiş `(P1, ε1, H1)`, `ΔP=P1−P0>0`, `Δε≥ΔP` varsayılsın. Kaynak uç değerleri korunarak içerideki her nedensel eğri şu sınırlar arasındadır:

`ε0+(P−P0) ≤ ε(P) ≤ ε1−(P1−P)`.

Pseudo-entalpi tanımı `dH=dP/[ε(P)+P]` ile bu iki eşitsizlik doğrudan integre edilir ve **zorunlu** entalpi aralığı elde edilir:

```
L = 0.5 * log1p(2 ΔP / (ε1 + P0 − ΔP))
U = 0.5 * log1p(2 ΔP / (ε0 + P0))
           L ≤ ΔH_native ≤ U
```

Bu sınırlar bir enterpolatör seçmeden, yalnız kaynak üçlüsünden türetilmiştir. `ΔH_native` sınırın dışına çıkarsa özgün `(P,ε,H)` uç noktalarının **tümü aynı anda korunarak** sürekli soğuk ve nedensel EOS kurulamaz. Aynı kaynakta `Δε≤0` veya `0<Δε<ΔP` ise zaten F77 kaynak-sekant zorunluluğu başarısızdır; F79, iki ayrı hatayı karıştırmamak için bu aralıklara ilaveten H nedensellik kararı vermez.

Daha zayıf **yalnız monoton ε(P)** zorunluluğu için de `log1p(ΔP/(ε1+P0)) ≤ ΔH ≤ log1p(ΔP/(ε0+P0))` koşulu kontrol edildi. Bu test basınç–enerji düğümleri artan olduğu hâlde kaynak entalpi artışının *herhangi monoton enerji ara eğrisiyle* bile uyuşmadığı aralıkları tespit eder.

## SHA-256 sabit özgün yedi EOS ve 323 gerçek dönen yıldız sonucu

| EOS | Özgün P,ε,H düğümü | Causal H aralık ihlali | Monotone-only H ihlali | Etkilenen özgün C yıldızı | F77'ye ek ret |
|:---|---:|---:|---:|---:|---:|
| APR4_EPP | 865 | 2 | 0 | 19 | 0 |
| ENG | 889 | 411 | 364 | 48 | 0 |
| MPA1 | 836 | 364 | 319 | 48 | 0 |
| MS1 | 895 | 338 | 321 | 48 | 0 |
| MS1B | 895 | 338 | 322 | 48 | 0 |
| WFF1 | 868 | 316 | 208 | 41 | 0 |
| WFF2 | 872 | 251 | 139 | 42 | 0 |
| **Toplam** | **6120** | **2020** | **1673** | **294** | **0** |

*Düğüm sayısının kesin toplamı çıktıya bağlıdır; her model ayrı gösterildi.* Bir yıldızda yalnızca **üst enerji düğümü gerçek merkez yoğunluğunun altında kalan tam kaynak aralıkları** sayıldı; yıldız merkezini geçen aralık yanlışlıkla ret üretmedi. Sonuç: F79'un entalpi sınırı, özgün nümerik EOS temsilinde yeni bir zorunluluk ihlali sınıfı gösteriyor, ama F77'nin 294/323 reddine **yeni yıldız ret sayısı eklemiyor**. APR4_EPP için yeni ilk H-gerek-şart ret aralığının üst enerji yoğunluğu `2.029865076e15 g/cm³`; F77'nin ilk çift-düğüm ışıküstü ret eşiğinden (~`2.053026e15`) daha aşağıda; ancak arada ekstra arşivlenmiş RNS yıldızı merkezi olmadığından mevcut 29 gözlemlenmiş düğüm-gerek-şart adayının sayısı değişmiyor.

Altı modelde düşük basınç H uyumsuzluklarının çoğu, F66'nın tespit ettiği LALSuite log-log spline tablosu anomalisiyle birlikte görülmektedir; hangi kısmın özgün mikrofizikten, hangi kısmın nümerik temsil ve H hesap ayarlarından geldiğini bu kaynak-NPZ düzeyi test **ayırt etmez**. Bir başka fiziksel EOS hipotezine geçmek, orijinal kaynak değerleri değiştirdiği için ayrıca etiketlenmeli, termodinamik ve mikrofiziksel olarak doğrulanmalıdır. APR4'ün az sayıdaki anomalisiyle diğer modellerin binlerce interval sayısını istatistiksel Bayes kanıt oranı olarak karşılaştırmak **yanlıştır**.

## Girdi güvenliği, kaynak ve sınırlama

- Orijinal JESTER commit `e6768650ce992abfd1153a6833857572fe5cd230`, yedi özgün `.npz` kaynak dosyasının SHA-256'sı, orijinal 7 C/RNS ZIP ve her 323 yıldız merkez yoğunluğu + spin toleransı kontrol edilir; yanlış/missing source fail-closed.
- Çift sayım yok: eski F38 7-EOS koşullu gözlemsel sıralaması yeniden hesaplanmadı, yeniden ağırlıklandırılmadı.
- Kaynak `h` LALSimulation pseudo-entalpisi olarak yorumlanır; bu tanım için resmi [LALSuite tabular EOS kaynak koduna](https://lscsoft.docs.ligo.org/lalsuite/dev/lalsimulation/_l_a_l_sim_neutron_star_e_o_s_tabular_8c_source.html) bakılır.
- Matematiksel bound hesapları IEEE double, `5e-15 + 1e-8*scale` güvenli toleranslı ve `log1p` kullanarak düşük basınç yuvarlama hatasını sınırlar; ilk testin hatalı sentetik H kaydırması düzeltilmiş, gerçek testte 18/18 PASS.
- **Kaynak-NPZ no-go ≠ fiziksel nükleer EOS'un evrensel geçersizliği.** 29 kaynak yıldızın *gerek-şart örneklemesi* geçmesi, sürekli fizik, gerçek BPS kabuğu, kimyasal µ0, baryon kütlesi, sabit-J kararlılık veya gerçek foton-likelihood sertifikası değildir.
- `physical_EOS_acceptance=NOT_ESTABLISHED`, `XPSI_source_photon_likelihood=NOT_RUN`, `physical_seven_EOS_Bayes=NOT_RUN`. MPA1/ENG/APR4 F38 sıralaması yalnız eski F38 koşullu sayısal model sınıfında geçerlidir.

## Yeni doğru bir sonraki deney

Değişmemiş kaynak EOS değerleri üstündeki H/P/ε tutarsızlığı gizlenmeden, farklı isimli fiziksel EOS modelinin aynı kaynak mikrofizik ve BPS kabuk içindeki `(ε,P,H,n)` termodinamik uyumunu ve faz/kimyasal potansiyel eşlemesini **tek ortak türetme prosedürüyle** sınamak; sonra yeni modelde gerçek 346.536369 Hz GR RNS sabit-J kararlılık ve X-PSI likelihood. F73'te başarısız olan doğrudan BPS–F67 geçişini yeniden başarılı ilan etmek yasaktır.

**Yeniden üretim:** `python -m unittest -v test_f79_enthalpy_causal_feasibility`; `python f79_enthalpy_causal_feasibility.py --source-dir source --artifacts-dir artifacts --source-manifest input/source_manifest.json --artifact-manifest input/archived_artifact_manifest.json --out F79_original_seven_enthalpy_causality_323_real_stars_20261120.json`.
