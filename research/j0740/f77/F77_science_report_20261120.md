# PSR J0740+6620 — F77: kaynak EOS sekantlarının matematiksel nedensellik zorunluluğu

**Tarih:** 20 Kasım 2026. **Yeni hesap:** 323 özgün dönen RNS C yıldızının her birinde, kaynak JESTER/LALSimulation **p–ε düğüm çiftleri** arasında yalnızca fiziksel *gerek şart* olan Δε≥ΔP>0 kontrol edildi. F75/F76'nın orijinal yıldızları, 12,9 GB Salmi foton arşivi, F38 KDE alanı veya 7-EOS skorları tekrar üretilmedi. Orijinal kaynak NPZ ve RNS artifacts SHA-256 ile kilitli.

## F77 yeni matematiksel kanıt

Kaynak EOS basıncı ve toplam enerji yoğunluğu `p, ε` iki değişkende de aynı geometrik `m^-2` birimindedir. Bir tek-değerli ve türevlenebilir fiziksel E(P) için `0<c_s²=dP/dε≤1` olduğundan `dε/dP≥1`. Bu eşitsizliği iki kaynak düğümü arasında integre edince **`ε_{j+1}-ε_j ≥ P_{j+1}-P_j > 0`** zorunlu çıkar. Kaynak düğümlerinin herhangi bir çiftinde `Δε≤0` (enerji monoton değil) veya `0<Δε<ΔP` varsa, **iki düğümün değerlerini koruyan hiçbir diferansiyellenebilir nedensel interpolant o aralığın tamamında geçerli olamaz.** Bu ortalama değer teoremi düzeyinde matematiksel bir **gerek şartın reddidir**. İki kaynak değerini değiştirerek yeni EOS kurmak ise ayrı hipotez, termodinamik ilk yasa/entalpi, TOV/RNS kararlılığı ve gözlemsel olabilirlik incelemesi ister.

Bir yıldızın yalnız **merkezine kadar bütünüyle dahil** olan kaynak aralıklarını test ettik: iki enerji düğümünün en büyüğü yıldızın gerçek kaynak merkez yoğunluğundan büyükse o aralık dışarıda bırakıldı. Dolayısıyla yıldızın tam merkezini aşan yarım-aralıktan ret üretilmedi. Ayrım toleransı `1e-10` göreli oran ile temkinli uygulandı. Aralığı geçen yıldız için interpolasyonla yoğunluk/yarıçap uydurulmadı.

## Gerçek kaynak ve gerçek yıldız sonuçları

| EOS | Özgün yıldız | Δε≤0 yıldız sayısı | Δε<ΔP ama Δε>0 yıldız sayısı | Herhangi gerek-şart ihlali | İhlal bulunmayan* |
|---|---:|---:|---:|---:|---:|
| APR4_EPP | 48 | 0 | 19 | 19 | 29 |
| ENG | 48 | 48 | 23 | 48 | 0 |
| MPA1 | 48 | 48 | 0 | 48 | 0 |
| MS1 | 48 | 48 | 0 | 48 | 0 |
| MS1B | 48 | 48 | 0 | 48 | 0 |
| WFF1 | 41 | 41 | 20 | 41 | 0 |
| WFF2 | 42 | 42 | 20 | 42 | 0 |
| **TOPLAM** | **323** | **275** | **82** | **294** | **29** |

**Çakışma:** 63 yıldızda hem negatif enerjili/monoton olmayan aralık, hem pozitif ama ışıküstü ortalama enerji-basınç eğimi bulundu. `275 + 82 - 63 = 294`. Bu satırlardaki yıldız sayıları *kaynak düğümlerine bağlı sayısal model* ret sayılarıdır; gerçek nötron yıldızı gözlem popülasyonu veya nükleer EOS mikro-fizik ret istatistiği değildir.

**Orijinal NPZ düzeyindeki tüm aralıklar:** APR4_EPP 0 negatif / 2 ışıküstü; ENG 1/59; MPA1 1/0; MS1 1/0; MS1B 1/0; WFF1 1/68; WFF2 1/78. Gerçek RNS yıldızının merkezinden yüksek basınçta bulunan aralıklar, o yıldıza ret olarak eklenmez.

**Yüksek yoğunlukta gerçek kaynak-NPZ sekant retleri:** APR4_EPP için ilk tam ret aralığının üst enerji yoğunluğu ~`2.053026×10^15 g/cm³`, 19 yıldız; ENG için ~`1.486542×10^15`, 23 yıldız; WFF1 ~`1.770023×10^15`, 20 yıldız; WFF2 ~`1.631716×10^15`, 20 yıldız. Bunlar yalnızca yerel c_s² spline düğüm anomalisi değil, kaynak oluşturulmuş **iki basınç-enerji düğümünün arasındaki fiziksel gerek-şart retleri**. F66'nın ham LALSuite `.dat` nükleer tablo satırları ile karıştırılmamalıdır.

## Önceki F66/F75/F76 ile kesin ayrım

- F66 doğrudan `lalsuite==7.26.4` ham mikrofizik tablosunun pozitif enerji-basınç eğimini doğruladı; altı modelde düşük-P negatif türev, orijinal LAL log-log kübik enterpolasyon katmanında oluşuyor. F77, bu enterpolasyonun **ürettiği** bazı NPZ düğümlerinde de enerji monotonluğu bozulduğunu buldu. Bu nedenle aynı NPZ düğümlerini sabit tutup yalnız PCHIP'e geçmek o segmentlerin nedenselliğini onaramaz; ham tabloyu temel alan yeniden fiziksel EOS üretimi gerekli olabilir.
- F75: 2,073 M☉ referans yıldızın kaynak-düğüm nedenselliği. F76: 323 gerçek dönen RNS yıldızın kaynak-düğüm taraması. **F77: kaynak düğümlerinin iki noktalı gerek şartı**, ilgili RNS yıldızına karşı kontrol; interpolatör-türevi olmadan yüksek yoğunlukta da ayrı ret.
- 29 yıldız için yalnız bu örneklenmiş aralıkların **gerek şartı geçmiştir**; sürekli EOS nedenselliği, termodinamik ilk yasa, sabit-J kararlılığı, foton X-PSI olabilirliği veya fiziksel Bayes olasılığı kanıtlanmaz.
- F38'in yedi sayısal modeli arasında MPA1–ENG–APR4_EPP koşullu sıralaması, **orijinal belirtilen model+önsel sınıfında** doğrudur; F77 bu eski sıralamaya fiziksel olasılık sertifikası vermez.

## Tekrar üretim ve kabul

```
python -m unittest discover -s . -p 'test_f77_*.py' -v
python f77_interval_causal_necessity.py --source-dir source --artifacts-dir artifacts --source-manifest input/source_manifest.json --artifact-manifest input/archived_artifact_manifest.json --out F77_original_323_source_interval_theorem_20261120.json
```

15 yeni bağımsız matematik/kenar-kurum testi PASS, gerçek 7 EOS ve 323 özgün yıldız kaynağı SHA-256 kabulü, kaynak gerçek verisinden tam JSON makbuzuyla karşılaştırma. İleride orijinal X-PSI foton analizi çalışmadan onu tamamlandı sayma.

**Resmî uygulama bağlamı:** [LALSuite tabular EOS C kaynak kodu](https://lscsoft.docs.ligo.org/lalsuite/dev/lalsimulation/_l_a_l_sim_neutron_star_e_o_s_tabular_8c_source.html), [X-PSI açık kaynak dokümantasyonu](https://xpsi-group.github.io/xpsi/index.html), [Salmi et al. 2024](https://doi.org/10.3847/1538-4357/ad5f1f).