# CANO — çekirdek mutasyon koruması karşılaştırmalı deneyi (8 Kasım 2026)

**Konu:** `organism.digital` · açık kabul kaydı: [GitHub #413](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/413) · mevcut Organism Lab sanal makinesi korunmuştur.

## Hipotez ve müdahale

Eski üç opkodlu genom `(COPY_REST, TASK_A, DIVIDE)` üzerinde her konumdaki mutasyon, genellikle kopyalama veya bölünme işlevini bozabilir. Bu nedenle TASK_B için faydalı olabilecek mutasyon bile yeni kuşaklarda seyrek görülüyor. Yeni `CoreProtectedWorld`, **orijinal `GenomeWorld._mutate` ile aynı rassal mutasyon çekilişlerini ve aynı beş seçenekli alternatifleri** uygular; ardından **sadece 0. ve 2. opkodlardaki structural çekirdek hasarını eski ebeveyn opkoduna geri çevirir**. Orta görev opkodu olduğu gibi kalır. İki koşulda TASK_B'ye geçiş olasılığı per-task-locus aynı kalır; hedefli biçimde TASK_B üretimi yapılmaz.

Bu bir *mühendis tarafından tasarlanmış mutasyon onarımıdır*, organizmaların kendiliğinden keşfettiği öğrenme değildir. Ayrıca orta konumdaki `COPY_REST` kopyalama boyutunu bozabildiği için çekirdek koruması **mutlak işlevsellik garantisi de değildir**.

## Önceden belirlenmiş karşılaştırma

- Her sette 30 bağımsız eşleştirilmiş tohum: **0–29** keşif, **30–59** önceden sabitlenmiş yeni tohum karşılaştırması. Her tohumda 4 grup (`unrestricted`, `protected_core`, `no_mutation`, `no_division`), toplam **240** deterministik simülasyon koşusu.
- 120 adım, 40. adımdan itibaren çevre A→B, kapasite 48, adım başına kaynak 1, baz mutasyon oranı %8. Ödül 2. Son 15 adım ayrı devam koşusunda mutasyon dondurulup ödül 1'e düşürülür; bu bağımsız/görülmemiş yeni görev değildir.
- Birincil ölçüt: son yaşayan nüfusta hem `TASK_B` hem de gerçekten kendini kopyalayıp bölen fonksiyonel genom oranı. Eşleştirilmiş korumalı − standart farkı.
- Sert bilimsel kabul: **tüm 30 tohumun en az %50'sinde** pozitif işlevsel fark + tek yönlü kesin işaret testinde p<0,05 + normal-approx %95 alt sınır >0 + zayıf ödül holdout nüfus farkı alt sınır ≥0 + iki negatif kontrol başarılı. Önceden olumlu sonucu garantilemez.

## Gerçek yerel sonuçlar

| Ölçüm | Tohum 0–29 | Tohum 30–59 |
|---|---:|---:|
| Korumalı – standart, olumlu tohumlar | 4/30 | 5/30 |
| Fark bulunmayanlar | 26/30 | 25/30 |
| Tek yönlü kesin işaret p | 0,0625 | 0,03125 |
| Standart kopyalanabilir genom payı, ort. | %41,38 | %43,56 |
| Korumalı kopyalanabilir genom payı, ort. | %100,00 | %100,00 |
| İşlevsel B oranı, standart ort. | %11,53 | %10,83 |
| İşlevsel B oranı, korumalı ort. | %13,06 | %16,32 |
| Çoğalma kapalı kontrol doğumları | 0 | 0 |
| **Sert genel uyum kabulü** | **BAŞARISIZ** | **BAŞARISIZ** |

*Yorum:* Korumalı çekirdek kopyalanabilirliği bu iki gözlenen tohum dizisinde yükseltti. Ancak daha az çeşitlilik ve bazı koşullarda daha küçük ortalama nüfus görüldü. Güven aralığı ve ağır ödül holdout sonuçları genel sağlam uyum lehine yeterli değil. İkinci sette işaret testi p<0,05 olsa da önceden belirlenen **%50 pozitif tohum** şartı ve tüm birleşik kapı geçilmedi. Tek başına p<0,05 gelişme kanıtı değildir. Bu sonucun dağılımı algoritmada seçilen mutasyon dağılımından etkilenir.

## Doğrulama ve açık kapılar

- Yerel izolasyon testleri: **8/8 geçti**; ilk test, orta görev lokusunda mutasyon olunca yapısal korumanın bile bazen işlevselliği bozamayacağı yönündeki **yanlış varsayımı** yakaladı; test düzeltilip tekrar geçti. Korunan opkodlar + RNG orta lokus eşitliği, deterministik devam, kısıtlar, SHA-256, atomik ve yinelenmeyen rapor yazımı, tam yeniden oynatma ve sahte özet reddi kontrol edildi.
- Kaynağın GitHub'da varlığı, PR/CI ve arşiv geri okuma sonuçları ayrı doğrulanmalıdır; yerel test tek başına GitHub başarısı değildir.
- Farklı kaynak bütçelerinde duyarlılık, gerçekten daha önce görülmemiş üçüncü görev üzerinde dayanıklılık ve mekanizma ablation testi açık. Altyapı üretim CANO, Render veya gerçek robotlarla karıştırılmamalıdır.