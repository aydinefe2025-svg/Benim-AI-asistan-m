# A01.01.51 — F66: Özgün EOS düşük-basınç negatif türev anomalisi, sayısal enterpolasyon kökeninin doğrulanması

**19 Kasım 2026 — yeni, kaynak-kilitli nümerik fizik analizi.** F58–F65 hesapları tekrar edilmedi veya değiştirilmedi. Bu çalışma **özgün yedi LALSuite EOS ham tablo kaynağını** LALSuite **7.26.4** kurulumu içindeki `lalapps/data/LALSimNeutronStarEOS_*.dat` dosyalarından okuyarak F65'in (SHA `6e35cd5ea33d3f3e9e3d0fb7cee585f809638e4b8507804bd7c0789148cd6e74`) gerçek 7 × 1.201 kaynak C fonksiyonu E(P), dE/dP sonuçlarını bağımsız yöntemle karşılaştırır.

## Kapanan kaynak-neden sorusu

LALSuite 7.26.4 içindeki 7/7 özgün iki-kolonlu EOS tablosunun ham basınç ve enerji düğümleri **monotondur**. ENG, MPA1, MS1, MS1B, WFF1 ve WFF2'nin seçilen **1×10⁻¹⁷–5×10⁻¹⁶ m⁻²** basınç aralığındaki **15 ham tablo satırı birebir aynıdır**. APR4_EPP'nin kullanılan ham tablosu 1.447 satır içerir; diğer altı modelin 102–126 satırlık tablosundan farklı örnekleme yoğunluğuna sahiptir.

Bağımsız yeniden üretim: ham EOS basınç ve enerji değerlerinin **ln(P) ve ln(E) eksenlerinde doğal kübik spline** kullanılması, gerçek LALSuite'in E(P) ve dE/dP sonuçlarını yedi EOS için de aynı 1.201 noktanın tümünde yüksek sayısal hassasiyetle yeniden üretir. En büyük bağıl enerji farkı **3.728e-15**; en büyük \(\max(1,|dE/dP|)\) ile ölçekli türev farkı **2.114e-13**. Altı modelin her birinde gerçek LALSuite ve yeniden üretilen spline **205/205 aynı basınç noktasında negatif türev** verir; APR4_EPP'de 0/0. Ham tabloda negatif basınç-enerji eğim adımı **0/7 modelde**. Bu nedenle F65 negatif türev bandının ham mikrofizik tablo düğümünden değil, kaynak değerlerini temsil eden **monotonluğu korumayan log-log kübik enterpolasyondan kaynaklandığı matematiksel olarak doğrudan yeniden üretildi**.

İlk **yanlış hipotez** gizlenmedi: P ve E'nin doğrusal eksenlerinde doğal kübik spline 205 negatif noktayı yeniden üretemedi; ilk CI fail-closed oldu ve bağımsız ZIP makbuzu korundu. Sonraki kurulumda dört doğrusal/logaritmik eksen seçeneği ve iki sınır koşulu (sekiz aday) sistematik karşılaştırıldı. Yerel basınç penceresinde **natural** ve **not-a-knot** kübik sınır koşulları aynı doğruluğu gösterebildiğinden bu bölge tek başına **sınır koşulunu tekilleştirmez**; arşivlenmiş LALSuite kaynak kodunda `gsl_interp_cspline` kullanımı ayrı iz sürme kanıtıdır. GSL/C sürümü kaynak satırının tam eşlenmesi bu deneyin dışında kalır.

**Yalnızca matematik duyarlılığı:** aynı artan ham EOS tablosuna `PchipInterpolator` uygulandığında bu seçilmiş F65 penceresinde yedi modelin hepsinde negatif dE/dP sayısı **sıfır**dır. Bu **yeni fiziksel EOS çözümü değildir**: entalpi H(P), baryon yoğunluğu n(P), kimyasal potansiyel, kararlı kabuk-core geçişi ve dönen GR yıldızı yeniden kurulup kanıtlanmadı. Ham kaynak EOS'un fiziksel geçerliliği veya gözlemsel kazanan ilan edilemez.

## Tablo (F66 gerçek kaynak dosyaları)

| Özgün model | Ham kaynak satırı | LAL negatif dE/dP | ln-ln kübik negatif | PCHIP tanısal negatif |
| --- | ---: | ---: | ---: | ---: |
| APR4_EPP | 1447 | 0 | 0 | 0 |
| ENG | 108 | 205 | 205 | 0 |
| MPA1 | 102 | 205 | 205 | 0 |
| MS1 | 122 | 205 | 205 | 0 |
| MS1B | 126 | 205 | 205 | 0 |
| WFF1 | 109 | 205 | 205 | 0 |
| WFF2 | 109 | 205 | 205 | 0 |

## Kanıt ve sınırlar

- Gerçek F66 CI kaynak deneyi: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44478645226 — **15/15 birim testi ve kaynak-denetim kabulü PASS**. Kanıt ZIP #14507711407 SHA-256 `42a0cc7f503c3e77c151fd88411ca2157a4f697dd95571eb93ef888c87be9d14`; ZIP CRC PASS; 40.336 bayt ham F66 JSON SHA-256 `a35e5fa383d505d88c5d196a830d03ce796b76c80cccce791b2c6713f62c9421`.
- Önceki **yanlış doğrusal P-E kübik hipotezinin reddi** aynı tarihteki ayrı CI hata arşivi ve ZIP SHA-256 `97e51b23e1d91821306911a8180976a42ccf5f16a01315f573d00b6b6f7e4f2f` ile korunmaktadır. Bu başarısızlık yeni log-log kaynak bulgusuyla karıştırılmadı.
- Tüm özgün 7 EOS `LALSimNeutronStarEOS_*.dat` dosyası kendi SHA-256 kimliğiyle F66 JSON ve kaynak makbuzunda izlenmiştir. JESTER F65 orijinal nükleer EOS bağı koparılmadı, F42 değiştirilmiş EOS kullanılmadı.
- **Yüksek yoğunluk bölgesi**, tüm EOS için nedensellik, yıldız dinamik kararlılığı, F64 baryon/entalpi ilk-yasa normalizasyonu ve X-PSI foton olabilirlik integrali **NOT_ESTABLISHED/NOT_RUN**. F66, bu açık işleri bitirdiğini iddia etmez; orijinal EOS isimleri altında farklı interpolantla sessiz düzeltme yapmaz.

**Bir sonraki fiziksel deney:** F65'in bozulan sayısal interpolantını farklı isimli, termodinamik bakımdan tutarlı ve kabuk eşleştirilmiş bir *hipotez* üzerinde kontrol etmek; PCHIP ile sadece dE/dP'nin negatif olmaması yeterli değildir. Ardından özgün foton bazlı X-PSI inference ve yedi kaynak fiziksel EOS'un önseli tekrar sayılmadan Bayes hesabı.
