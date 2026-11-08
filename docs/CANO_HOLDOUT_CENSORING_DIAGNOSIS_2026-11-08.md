# CANO — Birleşik görevde popülasyon tavanı / tabanı ölçüm körlüğü

**Tarih:** 8 Kasım 2026 · **Konu:** `organism.digital` · [Github #413](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/413) · durum: `tested`, **post hoc tanı**; özerk öğrenme ispatı değildir.

## Yeni ve ayrı sorun

[PR #429](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/429) ile gelen 450 koşuluk beş kollu A+B kompozisyon deneyi üç otuz-tohum dizisinin ikisinde **sıkı kabulü geçemedi**. İşlevsel A+B genom payı artarken 20-adımlık, enerji 3'e sıfırlanmış yeni görev ödülü altında son nüfus farkının güven aralıkları neden sıfırı içerebiliyor?

**Güncel tanı**, 450 çalıştırmayı **yeniden üretmeden**, bunların üç kaydedilmiş makine-okunabilir raporunu kontrol ederek yapıldı. Her rapor içindeki SHA-256 yeniden hesaplandı ve dıştaki sabit kaynak-rapor SHA-256 değerleriyle eşleştirildi. Bu sabitler **imza değildir**; Github kod/commit kanıtıyla beraber değerlendirilmelidir. Her 30-tohum × 5-grup kaydında kopya/eksik kol, sınır aşımı ve negatif kontroller denetlendi. Yeni Python modülü `organism_lab_cloud/organism_lab/holdout_censoring_audit.py`; mevcut modeller ve canlı genom checkpoint'i değiştirilmedi.

## Gözlenen, raporla eşleşen 90 eşleştirilmiş tohum

| Ölçüm | Sonuç |
|---|---:|
| Son nüfusta gramer-korumalı ve çekirdek-korumalı **eşit** | **87/90** |
| İki grup da azami kapasitede (48) | **65/90** |
| İki grup da tek hayatta kalan tabanda | **19/90** |
| Son nüfus eşit ama tavan/taban dışında | 3/90 |
| Gramer-korumalı daha yüksek A+B taşıyıcı payı ama eşit son nüfus | **55/90** |
| A+B işlevsel genom payı (gramer eksi çekirdek) | **+0,05602**, yaklaşık %95 aralık +0,02877 .. +0,08327 |
| Ödül alınan birey-adımlar (gramer eksi çekirdek) | **+30,08**, yaklaşık %95 aralık +3,32 .. +56,83 |
| 20-adımlık yeni görev sınaması doğumları (gramer eksi çekirdek) | **−1,48**, yaklaşık %95 aralık −2,32 .. −0,64 |
| Son nüfus (gramer eksi çekirdek) | **+1,21**, yaklaşık %95 aralık **−0,17 .. +2,60** |

**Sabit ve yorumu sınırlı koşullar:** 3 rapordaki toplam 90 farklı tohum, 5 grup/90 tohum=450 özgün koşu. Kaynak / kapasite seçimleri ve mutasyon önerileri önceki dört-lokus çalışmasının aynısıdır. Buradaki %95 aralıklar *yalnız seçilmiş deterministik tohumlara dayalı tanımlayıcı normal yaklaşımlardır*; gerçek dünyada istatistiksel genelleme iddiası değildir. Bu bir **yeni, müdahaleli deney değil**; önceden elde edilmiş sonuçların **geriye dönük** teşhisidir. Ölçümler korelasyon ve muhasebe farklarıdır; nedenin kesinlikle yalnız doygunluk olduğunu ispatlamaz.

## Sorun ve müdahale ayrımı

Mevcut son-nüfus ölçümü pratikte **doymuş**: 87 eşit sonucun 84'ü tavan ya da taban seviyesinde. Son-nüfusu tek başarı hedefi saymak, faydalı görev kombinasyonunu taşıyan organizmaların daha yüksek görev-ödülüne rağmen fark göstermesini engelleyebilir. Ödül alan birey-adımlar ortalaması artarken, ek doğumlar ortalaması azalmıştır; bu, tek bir "daha iyi" ölçüte indirgenemez. Doygunluk mekanizmasına **müdahaleyle** neden-sonuç atfetmek için farklı kapasite ve kaynak seviyelerine *önceden kayıtlı* bir sonraki koşuyu tasarlamak gerekir.

## Kanıt güvenliği ve test

- **TDD:** ilk kırmızı test yeni davranışın olmadığını gösterdi; ardından 8/8 yerel test yeşil, arşiv bozulması ve SHA hesaplanıp yeniden yazılmış sahte kayıt da reddedildi. Testler tam kaynak ve arşiv okuma yaptığı için mock sonuç üretmedi.
- **Girdiler:** `research_reports/organism-lab-transfer/energy-reset-seeds-0-29.json`, `energy-reset-seeds-100-129.json`, `forward-test-seeds-200-229.json`; girişlerin değişmez gövde SHA'ları `17a6141d…`, `8f20ceba…`, `54230779…`.
- **Çıktı:** `research_reports/organism-lab-holdout-forensics/holdout-capacity-audit-2026-11-08.json`; gövde SHA-256 `016f2ac019755fdc8554ee29323ceda68a5b454f5685091039e9d936c58c06dc`. Tohum bazlı 90 eşleştirilmiş kayıt, üç ayrı alt-küme, toplam muhasebe, sınırlamalar ve `adaptation_proven=false` içerir.
- **Kontrol:** `.github/workflows/cano-holdout-censoring-audit.yml` Python 3.11 ve 3.12'de gerçek JSON dosyalarıyla tekrar çalıştırıp raporun birebir çıktısını karşılaştırır. GitHub CI tamamlanmadan bu belgeye `ci_verified` denilmez.

## Bir sonraki anlamlı deney — *henüz yapılmadı*

Daha önce sonuç görmeden kabul eşiği sabitle: aynı eğitim sonunda **eşitlenmiş** popülasyon/enerji ve genom karışımı altında 20-adımlık görev C için kapasiteyi 24/48/64 ve kaynak bütçesini 0/1/4 olarak değiştir; erken zaman noktalarındaki yaşayan soy sayısını, C ödül miktarını ve ilk başarılı bölünmeye kadar süreyi izle. Pozitif etkiyi negatif kontrollere ve bütçe duyarlılığına göre raporla. Örneklem tekrarı, seçilerek raporlanan tohum ve yalnız son-popülasyon başarısı yasak. Birden fazla yeni basınç seviyesi kullanılırsa çoklu karşılaştırma sorunu açık yazılmalı. Başarı gerçek yaşam, robot, LLM kendi kendini eğitme değildir.
