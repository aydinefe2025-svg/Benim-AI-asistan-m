# PSR J0740+6620 — F78: yedi özgün JESTER EOS ve 323 dönen C yıldızında baryon yoğunluğu sütunu birinci-yasa ayrımı

**20 Kasım 2026. Yeni analiz:** Önceden F64, **MPA1'den türetilmiş 196 düğümlü RNS girdi tablosunda** `n ∝ epsilon` olgusunu ve iki gerçek RNS koşusunda M0 duyarlılığını göstermişti. **F78, önceki deneyi yinelemek yerine yedi ayrı özgün JESTER/LALSimulation NPZ dosyasının tamamında** kaynak `p,e,h,n` dizilerini doğrudan doğrular ve **323 özgün 346.536369 Hz RNS C yıldızının gerçek merkez yoğunluklarına** taşır. Hiçbir orijinal yıldız/foton arşivi/önsel/kanıt hesabı tekrar üretilmez.

## Kesin cebirsel zorunluluk

Kaynak dosyalarda `n/epsilon` **tüm 7 EOS içinde kaynak dizisi boyunca sabittir**, en fazla 2.3×10⁻¹⁶ bağıl sayısal sapmayla. Dolayısıyla bu `n` sütunu, enerji yoğunluğunun sabit bir kütle ölçeğine bölünmüş vekilidir; **başlı başına soğuk, korunmuş baryon sayısı yoğunluğu olduğunu çıkaramayız.** Soğuk barotropik birinci yasa `d epsilon=(epsilon+P) d ln n_b` gerektirir. Eğer `n=epsilon/K` ise `d ln n=d epsilon/epsilon` olur ve değişen epsilon ile P>0 bölgelerinde aynı anda doğru olabilmesi **P=0** gerektirir. Fiziksel yıldızın P>0 çekirdeğinde bu imkânsızdır. Kaynak adı altında `n` kullanarak doğrudan baryonik kütle veya önsel hesaplamak bu yüzden **geçersiz olabilir**.

## Yedi EOS'ta termodinamik entalpi ile bağıl biçim farkı

Kaynağın *kendi* `h` sütununu kullanarak soğuk birinci-yasa ile uyumlu **aday bağıl şekil** tanımlanır:

`n_H(P)/n_H(P0) = [(epsilon(P)+P)/(epsilon0+P0)] exp[-(h(P)-h0)]`.

İlk pozitif kaynak basıncı `P0`'da `n_H(P0)=n_proxy(P0)` eşitliği **keyfî normalizasyondur**: `mu_surface` veya bağımsız gerçek baryon yoğunluğu ölçülmemiştir. Kaynak `h(P)` aynı entegral ile hatasız tutarlılık göstermiyor olabilir, düşük P'deki bozuk E(P) ayrıca değişmez. Bu yüzden `n_H`, **fiziksel, kalibre edilmiş bir EOS değildir**. Her özgün C yıldızının merkez enerji yoğunluğu yalnız orijinal *bitişik* EOS düğümlerine log-enerji interpolasyonuyla eşleştirildi; bu işlem native LAL spline'ın tam tersini almak değildir. Sonuçlar yalnız kaynak-entalpi koşullu ve tanısaldır.

| Özgün EOS | C yıldızı | 323 yıldız dizisi içinde n_proxy / n_H **merkez medyanı** | 2.073 M☉'a en yakın kaynak yıldız merkezinde n_proxy / n_H | en üst kaynak düğümünde n_proxy / n_H |
| --- | ---: | ---: | ---: | ---: |
| APR4_EPP | 48 | 1.229830 | 1.235734 | 1.866579 |
| ENG | 48 | 1.205706 | 1.210645 | 2.326886 |
| MPA1 | 48 | 1.136749 | 1.140693 | 1.543264 |
| MS1 | 48 | 1.106523 | 1.109299 | 2.954295 |
| MS1B | 48 | 1.102243 | 1.105095 | 2.943523 |
| WFF1 | 41 | 1.195228 | 1.267044 | 1.684776 |
| WFF2 | 42 | 1.190065 | 1.229590 | 1.810434 |

**Yorum:** Bütün oranlar `n_proxy / n_H` şeklindedir; örneğin 1.14069, MPA1'de **aynı keyfî ilk düğüm normalizasyonu altında** yerel proxy'nin entalpi-temelli yoğunluk şekline göre %14.069 daha büyük olduğunu anlatır. Bu `%14.069` **baryon kütlesi hatası**, göksel mikrofizik ölçümü veya fiziksel gözlemsel posterior değildir. F64 MPA1 RNS 196-düğüm alternatifinde ayrı quadrature/koşullar altında +%13.913 bulmuştu; bu sonuç kaynak NPZ 836 düğümüne ve native `h` değerlerine aittir, karıştırılmaz.

Kaynakta **altı EOS'un her birinde n_H'nin azaldığı 1 aralık** bulunur; bu F66–F77 düşük-P sayısal spline anomalisinin ilk yasa uyumlu tüm eğri kurmayı engellemeye devam ettiğini gösterir. APR4_EPP n_H açısından monoton düğümlere sahiptir. Nitekim F77'nin yüksek basınç acausal kaynak düğümleri değişmedi. F78 bir EOS onarımı veya 323 yeni RNS koşusu **değildir**.

## Doğrulama ve kanıt

- Orijinal JESTER `e6768650ce992abfd1153a6833857572fe5cd230`; 7 EOS NPZ SHA-256 ve 323 kaynak C yıldızının orijinal artifact+JSON SHA-256 değerleri F75 makbuzlarına göre doğrulandı. Source-lineage uyumsuzluğu başarısız-kapalı.
- 16 adversarial birim test + tam gerçek kaynak hesabı; tam JSON SHA-256 ve kaynak alt küme medyanları ayrı pinned sertifikada.
- Yöntem: `f78_seven_eos_firstlaw_proxy_audit.py`. Uydurma bir sıfır basınç sınırı, M0 veya 7-EOS posterioru yazmaz.
- **Açık:** gerçek mikrofizik n_b(P) / µ(P) kalibrasyonu, sağlıklı kabuk–çekirdek ve faz geçişi, tüm P'de nedensellik, 346.536369 Hz sabit-J küresel kararlılık, özgün Salmi/NICER/XMM X-PSI foton olabilirliği ve nuisance marjinalizasyonu.

**Kritik bilimsel kural:** Önceki F38 model-içi MPA1>ENG>APR4 koşullu sayısal sıralamasını, veri miktarını iki kez sayarak veya bu `n` sütunuyla baryon-önsel eşleştirerek fiziksel EOS olasılığına dönüştürme.