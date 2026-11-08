# CANO — kaynak rekabeti, tarafsız yenileme ve görev maliyeti deneyi

**Tarih:** 8 Kasım 2026; **kapsam:** `organism.digital / issue #413 / resource competition`, üretim CANO'dan ve günlük üç-lokus genom zincirinden tamamen ayrı.

## Ölçülen neden ve kurallar

Önceki 450 deneyin 90 eşleştirilmiş tohumu içinde son nüfus çoğunlukla kapasite/taban seviyesindeydi. Orijinal `GenomeWorld` kaynakları sabit kimlik sırasıyla dağıtır, nüfus kapasiteye vardığında yeni doğum için boşluk kalmaz. Bu çalışma bu **iki ayrı yapısal kısıtın** (sıralama ve boş yer) kontrol edilebilir bir modelde etkisini ayırır. Orijinal `digital_vm.py` korunmuştur; bireylerin dış ağda çalışması, uygulama otomatik büyümesi, yapay zekâ ağırlıklarının eğitilmesi söz konusu değildir.

Orijinal VM'nin GitHub blob SHA'sı: `0ced308713956ebd43fa58ef29bb31502101d001`; yerelde ayrıca `git hash-object` ile birebir doğrulandı. Öğretilen/evrilen genom yok: 12 başlangıç bireyi **araştırmacının baştan verdiği** 4 A, 4 B, 4 A+B genomundan oluşur. Genomlarda mutasyon oranı **0**; böylece bu deney yeniliğin kendiliğinden keşfini değil **faydalı fenotip zaten varken seçilim mekanizmasını** test eder.

* Alternatif kaynak politikası: en eski kimlik önce (`seniority`) vs her adımda dönen dağıtım ve üreme önceliği (`rotation`).
* Kapasite politikası: kapalı (`closed`) vs tam doluyken **rastgele bir bireyin zorunlu çıkışı** ile bir boş yer açan `turnover`. Çıkış **fenotipe göre hedeflenmez**; yine de önemli, gerçek bir kayıp maliyetidir.
* A/B ortamı her 12 adımda sırayla değişir. Her organizmanın bakım maliyeti 1, başlangıç enerjisi 4, kaynak/adım 1, kapasite 12, zaman 80 adım. A+B fenotipi iki ortamda da görev ödülü alır. Eşdeğer bağımsız rastgele kaynak kontrolü yok; bu sınırlama kayıtta tutulur.
* Görev ödülü 2; görev maliyeti **0,1,2** ayrı gruplardır. Aynı başlangıç tohumuyla sıfır ödüllü ve sıfır maliyetli null kontrol karşılaştırılır. Maliyet 2 olduğunda net görev enerjisi 0: **ödüllü koşulun null ile birebir aynı iz vermesi negatif kontroldür**.
* Dört kol (`seniority_closed`, `rotation_closed`, `seniority_turnover`, `rotation_turnover`), üç maliyet × ödül/null, iki **önceden belirlenmiş** 30-tohum seti (600–629 ve 700–729). **Toplam 1440** koşu; ayrıca 60 bölünmesiz test koşusu kontrol amaçlı çalıştırılır. Enerji ve kaynak sınırları dış servislere uygulanmaz.

## Önden sabit ana karşılaştırma

Maliyet **0**, birleşik `rotation_turnover` ile eski `seniority_closed` arasında **nedensel A+B son payı farkı**: [ödüllü−null A+B payı] iyileştirmesinin iki politika arasındaki farkı. Önceden test edilen kabul: her 30-tohum grubunda en az 15 tohumda pozitif fark, tek yönlü kesin işaret testi p<0,05, normal-yaklaşık eşleştirilmiş fark %95 alt sınırı 0'dan büyük, dört negatif/koruma kontrolü başarılı. Maliyet 1/2 duyarlılık analizi; oradan sonradan bir kazanan seçilip ana iddia değiştirilmez. Bunlar proje içi önceden sabitlenmiş kurallardır, bağımsız bilimsel önkayıt değildir.

| Tohumlar | Pozitif/30 | p (işaret testi) | Ana fark (%95 betimsel aralık) | Turnover katkısı, seniority sabit | Rotation katkısı, turnover sabit |
|---|---:|---:|---:|---:|---:|
| 600–629 | **30/30** | 9.313×10⁻¹⁰ | **+0,3278** [+0,2609,+0,3947] | +0,3222 | +0,0056 |
| 700–729 | **29/30**, 1 negatif | 2.887×10⁻⁸ | **+0,3389** [+0,2276,+0,4502] | +0,2722 | +0,0667 |

**Sınırlı mekanizma kabulü:** Evet, bu *kuralları mühendislikle belirlenmiş sanal ortamda*, faydalı AB genotipinin **mevcut popülasyona yerleşmesini** yeni boşluk açarak artırmak mümkün. Bu genel evrim, otonom öğrenme veya gerçek dünya davranışı değildir. Bu sonuç, başlangıçta AB genotipinin bulunmasına dayanır.

**Görev maliyeti 1** duyarlılığında aynı ana politika farkı +0,2514 ve +0,2648; kaynak sırası etkisi +0,234/+0,297, turnover etkisi +0,017/−0,032 oldu. **Maliyet 2** için tüm 60 tohumda ödüllü/null nüfus izleri, soy sayıları ve doğumlar aynı; net avantaj **tam 0**. Bu negatif kontrol mekanizmanın ödül maliyetine duyarlı olduğunu destekler.

## ÖNEMLİ: maliyet ve güvenlik sınırlaması

* Deneysel nötr `turnover` kuralı **kapasite dolu kaldığı her adımda rastgele bir bireyi çıkarır**. Maliyet 0 altında 80 adımlık `rotation_turnover` kolunda 60 tohum ortalaması yaklaşık **80,7 ölüm / 80,7 doğum**dur. Yani kazanç yüksek *zorunlu kayıp/yenileme maliyeti* ile sağlanmıştır. Bu CANO üretimine uygulanacak bir politika **değildir**. Kaynakların dengeli dağıtılmasıyla zorla kayıp yaratmak birbirinden ayrılmalıdır.
* Aynı sanal modelin farklı tohumları bağımsız gerçek dünya gözlemleri değildir. İstatistik aralıklar bu sentetik tohumlara özgü betimsel değişkenliktir.
* Birey sınıfları sabit A/B/AB genomlarıdır; genetik mutasyon ve yeni özellik keşfi **kapalıdır**. Elde edilen kazanım **seçili bir yararlı genomun sıklık artışı**dır, genellenebilir yeni görev yeteneği değildir.
* Birleşik müdahale **iki kuralı birlikte** değiştirir; dört kollu deney ayrıştırıcı yan karşılaştırmalar sunar. Kaynak karşılaştırmasının kontrollü nedensel yorumu ancak belirlenen eşit koşullar içinde geçerlidir.

## Kaynaklar, doğrulama ve sonraki somut adım

Kaynak: `organism_lab_cloud/organism_lab/resource_competition.py`. Test: `organism_lab_cloud/organism_lab/tests/test_resource_competition.py`. Tekil tasarım red `NotImplementedError` → uygulama green görüldü; testte ayrıca ücretsiz kaynak sübvansiyonunun yoklama sonucunu bozması bulunarak test enerjisi sıfır kaynak altında doğrulandı. **11 yeni + 16 önceki = 27 lokal test başarılı.** Gerçek kaynak motoru orijinal SHA ile eşleşiyor; CI Python 3.11/3.12'de kaynak + iki raporun deterministik replay/hash'ini yeniden doğrulamak üzere tanımlandı. Raporlar `research_reports/organism-lab-competition/` altındadır; SHA imzalama değil bütünlük ölçümüdür.

Sonraki **ayrı ve henüz çalışılmamış** deney: güvenli/az maliyetli boşluk yönetimini `turnover` zorunlu ölümleri olmadan test et; öldürülen birey/yararlı genom seçilimi oranlarını birlikte önceden kabul kapısına dahil et, gerçek görev ve yeni spontan mutasyon için ayrı bir kontrol ekle. #413 yalnızca genellenebilir kalıtsal adaptasyon kanıtıyla kapatılabilir.
