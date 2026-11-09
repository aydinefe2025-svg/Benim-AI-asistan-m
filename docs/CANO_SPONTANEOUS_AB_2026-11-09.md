# CANO — A+B işlevinin başlangıçta verilmeden kalıtsal mutasyonla ortaya çıkışı

**9 Kasım 2026 · `organism.digital` · GitHub issue #413 · sadece sınırlı, deterministik simülasyon.**

## Ayrı deney; tekrar değil

Önceki [PR #442](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/442) ve [PR #452](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/452) deneyleri, başlangıç nüfusuna araştırmacı tarafından **A+B genotipini koymuştu**. Seçilim koşullarını ölçmüş, ama yararlı genotipin kendiliğinden mutasyonla doğduğunu göstermemişti. Bu yeni çalışmada 12 başlangıç bireyi **6 yalnız A + 6 yalnız B**, **başlangıçta A+B = 0**.

Orijinal `GenomeWorld` ve önceki `CompetitionWorld` / `VacancyWorld` kaynakları **değişmedi**. Yeni araştırma alt sınıfı dört-lokus `COPY_REST`, görev-lokusları, `DIVIDE` biçimini korur; her lokusta aday mutasyonu özgün motorun mevcut RNG mekanizması üretir. Yapıyı bozan adaylar reddedilir; mutasyon A+B'ye yönlendirilmez. Başlangıçtan farklı olarak çocuk genleri kalıtsaldır; doğum kimliği, ebeveyn genotipi ve nesil seviyesi ayrıca kontrol edilir. Bu, insanların tasarladığı bir gramer altında gerçekleşir; otonom evrim veya LLM ağırlık eğitimi değildir.

## Önceden kodda sabitlenen protokol

- İki ayrı yeni tohum aralığı: **1200–1229** ve **1300–1329**, toplam 60 tohum; 120 eğitim adımı, her 12 adımda `TASK_A` ↔ `TASK_B` ortam değişimi; nüfus üst sınırı 12, kaynak/adım 1, görev ödülü 2 ve maliyet 1.
- Beş kol/tohum: **uygunluk koşullu yer açma + mutasyon**, **kapalı yer + mutasyon**, **mutasyon kapalı**, **bölünme kapalı**, **eğitim görev ödülü sıfır**. Toplam **300 gerçek sınırlı simülasyon koşusu**.
- İlk A+B yavrusunun gerçek doğum adımı ve önceki ebeveyn genotipi, A+B taşıyan birey-adımları, A+B son yaşayan nüfus, mutasyondan doğan A+B sayısı, zorunlu boşluklar, doğumlar, ölümler, her adımın nüfusu kaydedildi.
- Eğitim boyunca A+B birleşimi ayrıca **ödüllendirilmedi**. Sonra mutasyon dondurularak her bireyin enerjisi 3'e eşitlendi; **20-adım A+B kompozisyonu için ödül 2 vs sıfır ödül** testi uygulandı. Bu bileşik görev daha önce ödüllendirilmemiştir, ancak yeni bir dış dünyadan/başka görev dağılımından gelen görev değildir. Holdout ödülünün kendisi ayrıca enerji maliyeti 1 ile dengelenmiyor; bu gerçek işletim maliyeti 1 altında uzun vadeli avantaj iddiası değildir.
- **Önceden sabit kabul:** her 30-tohum kümesinde A+B'nin mutasyonla >=15/30 tohumda ortaya çıkması; aynı kümede yer açma yönteminin kapalı yönteme göre A+B birey-adım farkının >=15/30 tohumda pozitif olması, kesin tek yönlü işaret testi p<0,05, eşleştirilmiş normal-yaklaşık %95 alt sınır >0; kompozisyon holdout farkının alt sınırı >=0; tüm negatif kontrollerin geçmesi. İki kümenin de geçmesi gerekir. Kabul koşulu sonuç görüldükten sonra değiştirilmedi.

## Ölçüm kapsamı: kanonik genotip ile işlevsel fenotip ayrı

**Bağımsız kod incelemesi (9 Kasım):** Raporun `ab_mutation_births`, `ab_final_count` ve `ab_person_ticks` sayaçları yalnız `(COPY_REST, TASK_A, TASK_B, DIVIDE)` sırasındaki **kanonik AB genotipini** sayıyor. Ters sıralı `(COPY_REST, TASK_B, TASK_A, DIVIDE)` de geçerli bir kopyalayıcıdır ve `novel_task_match` tarafından işlevsel A+B olarak tanınır, ancak bu kanonik sayaçlara dahil edilmez. Holdout C ödülü iki sıralama için de geçerlidir. Dolayısıyla aşağıdaki **5/60** gözlemi bütün işlevsel A+B fenotiplerinin toplam ortaya çıkış sıklığı olarak sunulamaz; yalnız kayıtlı kanonik genotip için güvenilir dar bir ölçümdür. Tüm işlevsel fenotiplerin frekansı ve olası sıralama etkisi yeni, kaynak-hashli, bağımsız sayımla ayrıca test edilmelidir. Tarihsel rapor ve önceden sabit kabul eşiği geriye dönük değiştirilmedi.

## Gerçek sonuç — pozitif yenilik var, ama genel gelişim henüz yok

| Ölçüm | Tohum 1200–1229 | Tohum 1300–1329 |
|---|---:|---:|
| **Mutasyondan doğan A+B bulunan koşul** | **4/30** | **1/30** |
| Mutasyondan doğan ilk A+B yavrusu | 4 | 1 |
| Son durumda yaşayan A+B bireylerinin toplamı | 26 | 12 |
| A+B birleşik görev ödülüyle sıfır ödüle karşı son nüfusu artan koşul | 4/30 | 1/30 |
| Yeni yer açma yönteminin kapalı yönteme göre AB birey-adım üstünlük gösterdiği tohum | 0/30 | 0/30 |
| İşaret testi (yeni yöntem üstünlük) | p=1,000 | p=1,000 |
| Yer açma yönteminde zorunlu kayıp toplamı | 0 | 2 |
| **Sıkı çoklu kabul kapısı** | **BAŞARISIZ** | **BAŞARISIZ** |

**Somut bulgu:** Başlangıçta hiç AB yokken, rastgele kalıtsal mutasyonlarla 60 tohumun **5'inde** kanonik AB genotipi ilk kez doğup yavrularına aktarılabildi. Bu beş koşulda yeni A+B taşıyıcıları bileşik görev ödülü verildiğinde ödülsüz karşıt koşula göre daha yüksek son nüfus gösterdi; burada seçilmiş olumlu alt-küme tüm popülasyona yaygın başarının kanıtı değildir. Tüm 60 koşulu kapsayan önceden sabit adaptasyon kapısı **BAŞARISIZDIR**.

**Yeni yapısal tıkanma:** Uygunluk koşullu yer açma, başlangıç A+B yokken çalıştırılan yeni deneylerde **ilk 30 koşulda sıfır**, ikinci 30 koşulda **toplam 2 kez** zorunlu yer açtı; kapalı politika ile ölçülen A+B birey-adımları her tohumda **aynı** çıktı. Bu, önceki koşuldaki hazır A+B ile gösterilen yenileme etkisinin, **yeni mutasyonun oluşma olasılığını ve yerleşmesini otomatik artırmadığını** gösterir. En olası model-içi neden, tam kapasite ve uygun bölünme enerjisi koşullarının seyrek çakışmasıdır; bunun kesin nedensel açıklaması ayrıca mekanizma düzeyinde test edilmelidir.

## Test ve kanıt kapsamı

- Lokal Python 3.13 üzerinde **6 yeni + 9 eski low-loss + 11 eski resource competition = 26/26 test başarılı**. Tasarım TDD: önce yeni `DiscoveryWorld` oluşturucusunun üç gerçek davranış testinde beklenen `NotImplementedError` gözlendi, uygulandı ve testler yeşile döndü. Kaynaklar derlendi.
- Bağımsız `verify_report` her raporu **kayıtlı parametreler ile baştan hesaplayarak** rapor SHA-256'sını doğrular; sonradan değiştirilmiş veri ve değiştirilip yeniden hesaplanmış sahte özet reddedilir. İki 30-tohum JSON'un **tam satırları** ve iki digest dış arşiv paketinde tutulur.
- Mevcut motor Git blob kimlikleri doğrulandı: 
  - `digital_vm.py` `0ced308713956ebd43fa58ef29bb31502101d001`
  - `resource_competition.py` `de430c7a2cf971a1cf1105c3f218c86ea3a251f5`
  - `low_loss_turnover.py` `e948fd99dd2939572834cde3ce416254e3ea0fef`
  - `compositional_transfer_study.py` `8fd857a39404602b86e2ae40f731ca0819862085`
- GitHub CI dosyası yalnız yeni kaynak kodu ve rapor özet manifesti üzerinden Python **3.11/3.12** ile 26 testi ve iki JSON'un baştan yeniden hesaplanan *hem gövde hem dosya SHA256* değerlerini doğrular. İlk yerel çalışma 26 test içeriyordu. Sonradan eklenen geçersiz ebeveyn soy kaydı regresyonuyla 27 odaklı test Python 3.11/3.12 GitHub CI içinde başarıyla yürütüldü; kaynak/rapor digest kontrolleri de aynı iş akışında çalıştı.
- Tam ham veriler, kod, test ve kanıt paketi ayrı araştırma arşivindedir; hiçbir Render PostgreSQL tablosu, servis dağıtımı, otomasyon, canlı organizma veya fiziksel robot değiştirilmeyecektir.

## Açık soru ve diğer projenin P0 engeli

1. Yeni genotip doğum sıklığı **%8 mutasyon oranında** neden yalnız 5/60? İlk AB doğumunun beklenen mutasyon yollarını ve soy kapasitelerini ayrı eşleştirilmiş deneyle ayır; örneklem sonrası yeni eşik uydurma.
2. Uygunluk-koşullu yer açma çalışmayınca, yeni genotiplerin kalıcılaşmasına yardım edecek **kayıpsız** üreme kotası ya da kaynak sunumu tasarla; önceden belirlenmiş kapasite/enerji bedeliyle yeni tohumlarda test et.
3. Render PG18 gerçek yedeği **ayrı kritik P0**: [GitHub #440](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/440) — DB açık fakat dış bağlantı güvenlik duvarı kapalı, mevcut Neon PG18 vault kayıtları gerçekte Neon PG17 kaynağından geliyor. Bu deney, o yedeğin yerine **geçmez**. Gerçek şifreli PG18 dökümü+farklı sağlayıcı geri okuması+izole geri yükleme olmadan bu P0 bitmiş sayılamaz.
