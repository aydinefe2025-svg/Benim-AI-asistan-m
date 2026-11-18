# A01.01.51 — F63 özgün MPA1 sabit-J dönüş noktası, iki uzaysal ızgara ve **birebir aynı EOS tablosu**

**18 Kasım 2026 — gerçek RNS C genel görelilik hesapları, nihai yedi-EOS Bayes hesabı değildir.**

## Yeni doğrulanmış fiziksel-sayısal sonuç

Özgün, enerji-lift ile değiştirilmemiş JESTER/LALSuite **MPA1** NPZ'nin SHA-256'sı `0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22`. Sabit açısal momentum **J=6.104310398721e+48 g·cm²/s**; başlangıç J değeri F62'nin 2,073 M☉, yaklaşık 346,54 Hz gerçek RNS yıldızında doğrudan RNS C'nin `star.ang_mom` çıktısından çıkarıldı. Bu kütle, aynı J dizisindeki örneklenmiş kütle maksimumunun düşük-merkez-yoğunluğu tarafında kalıyor.

- **151×301** uzaysal çözünürlük: **27/27** farklı merkez yoğunluğunda doğrudan sabit-J C/RNS yıldızı. Örneklenen tepe M=`2.475801860` M☉, merkez yoğunluğu `2.102e+15` g/cm³, eşekvator yarıçapı `11.369861115` km. Tepe öncesi ve sonrası komşu kütleleri daha düşük, dolayısıyla **sabit-J kütle dönüş noktası çevrelendi**.
- **201×401** uzaysal çözünürlük: önceden belirlenmiş tepe çevresinde **7/7** gerçek sabit-J C/RNS yıldızı; örneklenen tepe M=`2.475205943` M☉, merkez yoğunluğu `2.102×10¹⁵` g/cm³. Yine kütle maksimumu komşuların içinde.
- **Kritik eşleşme:** her iki ızgarada kullanılan RNS termodinamik EOS dosyasının **baytları birebir aynı**, SHA-256 `15cd0e83830635fe46264ff5e5c52f97f4b8846dc73c1a64768e1237417d9e51`. Bu kapı, ayrı iş akışı koşularının yazdırma/NumPy kaynaklı son-onalık tablo farklarını dışlar. İki ızgara için modelin EOS düğüm sayısı 196'dır.
- 7 eşleşmiş yıldızda en büyük mutlak kütle farkı `0.000597465` M☉ ve yarıçap farkı `1.043699` m. Bu değerler **iki-ızgara duyarlılık ölçüsüdür**, genel sayısal hata üst sınırı veya fiziksel ölçüm hassasiyeti değildir.

| Merkez yoğunluğu (×10¹⁵ g/cm³) | 151×301 M/M☉ | 201×401 M/M☉ | ΔM/M☉ (ince−kaba) | ΔR (metre) |
|---:|---:|---:|---:|---:|
| 2.048 | 2.475496953 | 2.474905734 | -0.000591 | -0.9618 |
| 2.066 | 2.475661004 | 2.475068182 | -0.000593 | -0.9831 |
| 2.084 | 2.475762976 | 2.475168545 | -0.000594 | -1.0039 |
| 2.102 | 2.475801860 | 2.475205943 | -0.000596 | -1.0241 |
| 2.120 | 2.475789142 | 2.475191677 | -0.000597 | -1.0437 |
| 2.138 | 2.474919355 | 2.475119588 | +0.000200 | -0.2286 |
| 2.156 | 2.474682490 | 2.475002441 | +0.000320 | -0.0819 |

## Gerçek sınırlamalar ve yanlış yorumları engelleyen kapılar

**Özgün MPA1 mikro-fiziksel olarak sertifikalı değil:** düğüm #254'te ρ=`3.3242342e+11` g/cm³, `c_s²/c²=-0.17517448`, enerji tersliği kenarı #253. EOS dönüşümünde kusurun düğüm atlanması yoluyla ortadan kaybolması, fiziksel iyileştirme sayılmadı. Orijinal `n=e/m_avg` yaklaşımı, tam baryon birinci yasa kalibrasyonu olarak değerlendirilmedi.

**Örneklenmiş sabit-J dönüş noktası dinamik/radyal/eksensimetrik kararlılık simülasyonu değildir.** Yıldızın tüm kararlı dalını, bütün sabit-J olasılıklarını veya süreklilik boyunca her yoğunluğu kanıtlamaz; turning-point ilkesi gerekli fiziksel hipotezleri gerektirir. MPA1 özgün fiziksel geçerlilik sorunu çözülmeden bu sonuç EOS Bayes ölçütü olarak kesin kabul edilemez. Salmi/X-PSI kaynak-native photon/nuisance olabilirliği, 7 özgün nükleer EOS kanıt faktörleri ve çift sayılmayan model posterioru **NOT_RUN**.

## Kanıt ve kaydı

- GitHub F63 PR #623: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/623
- Gerçek F63 son CI: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44397730870
- Önceki fizik kontrolü F62 merge: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/621
- Coarse SHA-256 JSON `681900f1e582815ccc7a0d6b73223b2211e767b96f2c7ff73641aedf44b12e0b`, CI ZIP `0faa0f78a4b5b9a48def4c90dd945acc4a5dee7e2f95fca329c4bb4a510c057e`.
- Fine SHA-256 JSON `f9f2af9b56a018d455a856dd210bf0bc82a67ec1971fc7756aafaf962dc5c79b`, CI ZIP `2230431bd52042fb0443d7f2094b4ef18b6300783c3c0e02b800e45228f24523`.
- Kontrol: iki ZIP CRC başarılı; 27 + 7 yıldız kabulü; her iki EOS tablo SHA eşleşmesi; X-PSI ve Bayes iddiası yok. Bunlar tamamlanmadan hiçbir `EOS solved` etiketi kullanılmamalıdır.

**Sonraki zorunlu fiziksel iş:** negatif EOS kabuk türevinin kaynak-kilitli fiziksel/numerik ayrımı ve güvenli çekirdek-kabuk mikro-fiziksel eşleme; sonra dönen yıldızda konverjans/kararlılık ve 7 modelin gerçek X-PSI ortak olasılık hesabı. F58–F63'te tamamlanan hesaplar yeniden raporlanıp başarı sayılmamalıdır.
