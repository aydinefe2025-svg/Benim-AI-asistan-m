# A01.01.51 — F69: F67 sayısal MPA1 adayının koşullu ⁵⁶Fe yüzey tamamlama deneyi ve gerçek statik GR baryon hesabı

**19 Kasım 2026.** Bu veri **özgün nükleer MPA1 değildir**, F67'nin ayrıca tanımlanmış PCHIP soğuk EOS'unu düşük basınçta açıkça değiştiren, **yeni ve koşullu bir fizik varsayımıdır**. F58–F68 özgün kayıtları/denklemleri değiştirilmedi. Kaynak F67 termodinamik EOS tablosunun SHA-256'sı `d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22`.

## Önceki eksik nasıl ayrıştırıldı?

F67'nin ilk basınç düğümünde rho = **7.757233981433 g cm⁻³**; sıcaklıksız kristal ⁵⁶Fe sıfır-basınç sınır varsayımında rho_surface = **7.86 g cm⁻³** (Potekhin et al. A&A 2013). Mevcut F67 P(E) eğrisinin monotonluğu bozulmadan Fe yüzeyle doğrudan eşleşmesi **imkânsız** çünkü ilk düğümde enerji yoğunluğu yüzeyden düşük (fark %-1.307456). Önceki sonuç 'fiziksel kabuk onarıldı' diye etiketlenemez.

Bunun için **MPA1_PCHIP_COLD_FE56_SURFACE_V1_CONDITIONAL_NOT_ORIGINAL** adlı ayrı aday oluşturuldu. EOS aşağıdaki düşük-P aralığında değiştirildi, üzerindeki bütün F67 kayıtlı düğümler korundu:

- Eşleme p_m = `5.684450283147875e-35 m⁻²` geometrize basınç, F67'nin 2425-noktalı kaynak gridinde indeks 68 (0-based), rho_m = `8.035723529936 g cm⁻³`.
- E(P) = E_Fe + (E_m − E_Fe) (P/P_m)^α, α = **0.937812930396**, 0≤P≤P_m. E(P) ve dE/dP ikisi de p_m'de yeni ve üstteki F67 sayısal EOS ile süreklidir (C¹). Her iki parçada P≥0, E>0, örneklenen alt bölgede 0<c_s²/c²<1.
- ⁵⁶Fe atom kütlesi NIST 55.93493633 u; 2022 CODATA u=1.66053906892×10⁻²⁷ kg. Yüzey baryon kimyasal potansiyeli **930.411846 MeV** *varsayımıyla* H(P)=∫₀ᴾdP/(E+P), µ(P)=µ_Fe exp(H), n(P)=(E+P)/µ(P) hesaplandı. Bu fiziksel yüzey varsayımına **KOŞULLU** mutlak n(P) verir; kaynağın bağımsız n_b ölçümü değildir.
- n_b(P=0)=**4.738908539e+30 m⁻³**, F67'nin ilk pozitif basıncına denk yeni n_b ≈**4.739141858e+30 m⁻³**; düşük-P Fe ek tabakasının H artışı **9.6280223829206e-12**.
- Soğuk ilk-yasanın üst F67 tablosuyla ayrı türev/sonlu-fark çapraz kontrolü ≤**3.656e-07** bağıl hata. Bu, fiziksel β-dengeyi değil tanımlanmış sayısal barotropun termodinamik özdeşliğini sınar.

## Gerçek Einstein TOV baryon integrali (iki bağımsız form)

Her yıldızda (r,m) ve (u=r²,v=m/r) ile **bağımsız** statik Einstein TOV çözümleri ve eşzamanlı baryon sayısı B = m_u∫4πr² n_b/(1−2Gm/rc²)¹ᐟ²dr hesaplandı. Rest-baryon kütlesinde m_u kullanılması **ayrıca belirtilen birim konvansiyonu**, gözlemsel baryon kütlesi ölçümü değil. Sıfır-basınç yüzeye kadar ince Fe tabakası birinci mertebe analitik bağlandı.

| Mg hedef (M☉) | Mg gerçek (M☉) | Statik R(p_m) km | **Koşullu M_b (M☉)** | M_b−Mg (M☉) | İki bağımsız B farkı (M☉) |
|---:|---:|---:|---:|---:|---:|
| 2.073 | 2.072999964 | 12.406156007 | **2.421825108** | 0.348825144 | 4.5575e-07 |
| 2.175 | 2.175000127 | 12.322892403 | **2.567309080** | 0.392308953 | 3.4600e-07 |
| 2.200 | 2.200000039 | 12.296156982 | **2.603617866** | 0.403617828 | 2.3627e-07 |
| 2.250 | 2.250000004 | 12.232611893 | **2.677086700** | 0.427086696 | 1.1628e-08 |

Eksik dış tabakanın **ilk-mertebe** R katkısı en fazla `2.452142651e-07 m` (~0.2452 mikrometre); gerçek RNS 151×301/201×401 yakınsama farkları metre mertebesindedir. Alt kabuk kütlesi birinci mertebe tahmindir; kesin aralık ispatı değildir.

**ÖNEMLİ NORMALİZASYON DUYARLILIĞI:** Üstteki sayısal E(P) sabit tutulup Fe yüzey µ₀ varsayımı +%1 değiştirilirse hesaplanan B doğrudan 1/1.01 ile çarpılır. Bu, kaynağın µ₀ içermediği durumda baryonik kütlenin tekil olarak belirlenemeyeceğini gösterir. Örneğin 2.073 M☉ yıldız için B=2.421825108 M☉, aynı E(P) ancak +%1 µ₀ koşulunda B=2.397846642 M☉. **Her iki sonuç da koşulludur.**

## Kanıt ve sıkı sınırlar

Bu çıktı **orijinal MPA1’in tam fiziksel kabulü DEĞİL**, bağımsız katı kabuk bileşimi veya faz geçişi kanıtı **DEĞİL**, rotasyonel F69 RNS B hesaplaması **DEĞİL** ve NICER/XMM foton-native X-PSI + yedi **özgün** EOS Bayes hesabı **DEĞİL**. Bu açık meseleler `NOT_ESTABLISHED` veya `NOT_RUN` kalır.

Kaynak: [NIST Fe-56 kütlesi](https://physics.nist.gov/cgi-bin/Compositions/stand_alone.pl?ascii=ascii&ele=Fe), [CODATA 2022 u](https://physics.nist.gov/cuu/pdf/JPCRD2022CODATA.pdf), [A&A 2013: cold catalyzed Fe surface density](https://doi.org/10.1051/0004-6361/201321697). Kaynak kod, 18 fail-closed test, tüm yeni EOS tablosu, dört kütle ham JSON ve SHA-256 manifest ayrı. Dış kabuk modelini kaynak özgün etiketle kullanmak yasaktır.
