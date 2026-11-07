# CANO — kalıtsal çeşitlilik ve uyumun dürüst kabul testi (8 Kasım 2026)

**Ana takip:** [GitHub Issue #413](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/413).

## Önceki çalışmanın yeniden kullanılması

Var olan `organism_lab_cloud/organism_lab/digital_vm.py` dünyası `COPY_REST`, `DIVIDE`, `TASK_A` ve `TASK_B` kodlarını zaten uyguluyor; `adaptation_study.py` de 2 kollu A→B ortam değişimi deneyi içeriyor. Bunlar yeniden yazılmadı. Eklenen `adaptation_validation.py` modülü **üç kol**, kaynak ve kapasite denkliği, genom işlevselliği, nesil kohortları, mutasyonu dondurulmuş ödül-azaltma testi ve tüm koşulların SHA-256 + deterministik hesapla geri doğrulamasını sağlar.

## Sabit deney tasarımı

- 30 eşleştirilmiş tohum (0..29), her koşulda 120 adım, 40. adımdan sonra ortam `TASK_A` → `TASK_B`.
- Her tohum için `mutation` (%8 işaret mutasyonu), `no_mutation` (%0) ve `no_division` (%0, çoğalma kapalı) kolları; toplam 90 koşu.
- Nüfus sınırı 48, adım başına kaynak 1, görev ödülü 2.
- Ana ölçüm: yaşayan nüfusta *hem TASK_B taşıyan hem de gerçekten kopyalanıp bölünebilen* genom oranı; nesli tükenmişte 0. Yan ölçüm: deney sonunda genom mutasyonu dondurulmuş, TASK_B ödülü 1'e düşürülmüş 15 adımlık dayanıklılık deneyi nüfusu. Bu yeni görev/bağımsız tür sınaması değildir.
- Kabul: iki eşleştirilmiş ortalama farkın yaklaşık %95 güven aralığı alt sınırı >0, benzersiz genom artışı >0, bölünmesiz kontrolde doğum = 0, *en az yarı* tohumda işlevsel TASK_B artışı, ayrıca tek yönlü **kesin işaret testi** p<0,05.

## Doğrulanmış yerel hesaplama (depo CI ayrıca gerekir)

| Ölçüm | Sonuç |
|---|---|
| Mutasyonlu kolda son ortalama benzersiz genom | 3,2667 |
| Mutasyon kapalı kolda son ortalama benzersiz genom | 1,0000 |
| İşlevsel TASK_B oranı eşleştirilmiş ortalama farkı | +0,11528 (yaklaşık %95 GA +0,00816 .. +0,22240) |
| Düşük ödüllü testte ortalama nüfus farkı | +8,667 (yaklaşık %95 GA +3,159 .. +14,174) |
| Tohum bazında işlevsel TASK_B artışı | **4/30**; 26/30 fark yok |
| Tek yönlü kesin işaret testi | **p=0,0625** |
| Bölünme kapalı kolda doğum | 0 |
| **Sıkı sağlamlık kabulü** | **BAŞARISIZ — genel uyum henüz kanıtlanmadı** |

## Önceden sabit kabul kapısıyla bağımsız yeni tohum kontrolü

Sıkı kapı (pozitif tohum oranı >=%50, kesin işaret testi p<0,05 ve diğer koşullar) sabitlendikten sonra, ayrı başlangıç tohumları **30..59** ile 90 yeni simülasyon çalıştırıldı; önceki gruptaki sonuçlara uyacak şekilde eşikler değiştirilmedi.

| Bağımsız kontrol 30..59 | Sonuç |
|---|---|
| İşlevsel TASK_B artışı gösteren koşul | **4/30** |
| Diğer tohumlar | 26/30 sıfır fark |
| Kesin işaret testi | **p=0,0625** |
| Ortalama işlevsel TASK_B artışı | +0,10833; yaklaşık %95 GA +0,00771 .. +0,20895 |
| Zayıf ödül koşulunda ortalama nüfus farkı | +8,0333; yaklaşık %95 GA +2,4606 .. +13,6060 |
| Negatif kontrol doğumları | 0 |
| **Sıkı kanıt kapısı** | **BAŞARISIZ** |

İki ayrı 30-tohum dizisinde yalnızca 4'er tohumun olumlu çıkması, ortalama pozitif olsa da kazanımın örneklemlerin küçük kısmına yoğunlaştığını gösterir. Bu nedenle çoğunlukta genellenebilir gelişim **kanıtlanmamıştır**. İkinci dizi, keşif verisi görüldükten sonra ilan edilen güçlü ölçüte karşı ayrı tohum kontrolüdür; *ön kayıtlı bilimsel bağımsız hakemli çalışma değildir*.

**Kritik yöntem dürüstlüğü:** İlk 30 tohumluk keşif sonucunda ortalama fark pozitif görünüyordu. Sonra seyrek başarı sorununu keşfedip çoğunluk ve kesin işaret testi kapılarını güçlendirdik. Bu nedenle **yeniden incelenen bu 30 tohumluk örneklem önkayıtlı bağımsız doğrulama değildir**. Yeni tohumlar, farklı görevler ve dış doğrulama gereklidir. Bu modelde bazı koşullarda genetik değişim ve görev uyumu görüldü; kullanıcının istediği genel, kendi kendini öğrenerek gelişen sistem henüz kurulmuş değildir.

## Gerçek kabul kapıları ve sonraki adım

1. GitHub CI'da gerçek `organism_lab_cloud` motoruyla Python 3.11 ve 3.12 üzerinde tam çalıştırma, 90 kayıt doğrulama ve yeniden hesaplama.
2. Ana rapor JSON'unun SHA-256, test komutu, kod SHA ve arşiv geri okuması.
3. Kaynak bütçesi duyarlılık taraması ve **önceden tanımlanmış** yeni görev/gerçek çevre holdout mekanizması. Yeniden ilk veri setine eşik ayarlama yok.
4. Canlı gözlemevine başarılı kanıt olmadan “öğrendi/uyumlandı” etiketi koyma. Gerçek `main` üretim CANO, yaşayan biyoloji ve robotik üretimle karıştırma.