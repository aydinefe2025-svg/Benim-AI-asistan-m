# J0740 — resmî Salmi kaynak eşleşmesi: basename hatasına karşı güvenli doğrulama

**14 Kasım 2026 / A01.01.50 / P0 bilimsel kaynak veri kimliği**

## Yeni doğrulanan durum

1. Orijinal Salmi 2024 Zenodo **README**, `J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat` dosyasını **ana** `STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/` koşusuna bağlar. Ana çalıştırıcı `STU/STU_NICER_XMM_hr/STU_modules/main_lp40k_Xse001_Dfix.py`, 40.000 canlı nokta, 0,01 örnekleme verimliliğidir. `GAMMA` veri/cevap dosya adları ve `ST-U` fiziksel model dizinini sırf adları farklı diye ayrı koşular sanmak yanlış olabilir. Resmî kayıt: <https://zenodo.org/records/10519473/files/README.md?download=1> (README MD5 `ed363c6d252a0a6ef177f8d45757e50e`).
2. Makale bütün koşular için X-PSI `v0.7.10`–`v1.2.1`, ana yayın sonucunda `v1.2.1` bildirir. Eski saklanan bir `out_` günlüğünde `v1.2.0` gözlemlenmişti. Bu çelişki saklıdır: kesin koşu sürümü ana metin başlığına bakılarak uydurulmaz; SHA doğrulanmış **o koşunun** `out_` satırından okunur. <https://doi.org/10.3847/1538-4357/ad5f1f>.
3. `xpsi-group/xpsi` resmî GitHub etiketleri doğrudan karşılaştırıldı: `Prior.py` SHA **1f68f367efc188637816bcf81ca6451ba528d2f1**, `NestedSampler.py` SHA **acba178f870ddcf4fc800041ffbe7b1c448c7c4e**, `Sample.py` SHA **10614946cac98250fb6572d2815db2410c937cd8** her iki sürümde birebir aynı. `Likelihood.py` bütününde fark var (`v1.2.0` SHA **989b2288d76879c1052efef0b4871c4337c3a780**, `v1.2.1` SHA **b01c1bf2e4736d97529532aa35f88b393ce55150**), fakat önsel kontrolü ve `loglikelihood + logprior` hesaplayan `__call__` fonksiyonunun incelenen 106 satırı birebir aynı. **Bütün X-PSI fizik modüllerinin eşitliği kanıtlanmadı.**
4. Önceki bağımsız Windows kanıtı, aynı ana çıktı klasöründeki noMM adındaki `stats.dat` ile `out_` günlüğünün `logZ` ve hata değerlerini yazdırılan hassasiyette eşleştirmişti: `−21889.9868120139290` / `−21889.9868120139`; hata `0.0244091345940078905` / `0.02440913459400789`. Bağlantı **kuvvetli**, her örneğin özgün tarihî çalıştırma sürecine kriptografik olarak bağlandığı iddiası değildir. Bu kayıt, mevcut GitHub #280 kaynak raporundan alınmıştır.
5. Mevcut `research/j0740/source_lineage_gate.py` içindeki `SOURCE_POSTERIOR_RUN in config` zorunluluğu, README'nin belgelediği gerçek ana çalışma için **yanlış negatif** üretebilir. Çünkü çıktı dizininin asıl adı `run1_lp40k_Xse001_Dfix`, yayımlanan M,R dosyasının kısaltması farklıdır.

## Uygulama

`headline_run_binding.py` resmî klasör eşleştirmesini tanır; eski eşleştirme fonksiyonunu veya bilimsel kaynakları sessizce değiştirmez. **Gerçek dosyalar verilirse** aşağıdakileri baştan doğrular:

- 40,6 MB orijinal arşivin resmî MD5 kimliği;
- resmî Zenodo README için sabit beklenen MD5; **yalnız dosya yolu da verilirse** README baytlarının MD5 yeniden okuması (salt metin metadata ile yeni hash kanıtı üretmez);
- özgün çalıştırıcı, `CustomPrior`, ayarlar, `out_` ve `stats.dat` için önceden bağımsız Windows denetimleriyle kaydedilmiş **beş SHA-256**;
- orijinal tar içindeki **tam beş göreli yol**;
- `out_` içinde gerçekten yazan X-PSI sürümü ve yayındaki sürüm aralığı;
- bağımsız `stats.dat`–`out_` MultiNest `logZ` ve hata değerlerinin tolerans içi eşitliği **ve önceden kaynakla eşleştirilmiş özgün logZ/hata değerlerine ayrı ayrı bağlılığı**;
- isteğe bağlı 12,9 GB tam kaynak arşivi yeniden MD5 doğrulaması (gerçek bütçe/çalışma durumuna göre).

Test sırasında gerçek üretim hash'leri **yalnız sentetik test fixtürü için** değiştirilebilir; bu durumda sonuç asla bilimsel olarak kaynak-doğrulandı ibaresini vermez.

### Kanıtlı testler

`python -m unittest test_headline_run_binding.py -v` — **10/10 PASS**. RED kaydı: olmayan resmî eşleştirme davranışında `NotImplementedError`; GREEN kaydı: yöntem eklenince aynı test PASS. `python -m compileall .` PASS.

## Sınır (gizlenmeyecek)

Windows SentinelX son kontrolde **OFFLINE** olduğundan, bu dosyanın üretim hash denetleyicisi gerçek dosyalarda bu turda çalıştırılamadı. Kodun **test başarısı**, yayımlanan örneklerin kaynak önseli ve EOS veri zincirinin tam doğrulandığı anlamına gelmez. Özellikle 15-boyutlu kaynak foton olabilirliğinin tüm kütle–yarıçap düzlemindeki yakınsaması, tüm yedi orijinal EOS için sürekli dönen yıldız kararlılığı ve EOS Bayes sonucu tamamlanmış değildir. `EOS_Bayes=NOT_RUN`.

Kod, test, RED/GREEN kayıtları ve SHA manifesti aynı paket içinde sağlanır. Ana çalışma dalına ayrı dosyalar olarak eklenmeli; eski keskin kapı ancak gerçek kaynak dosyalarıyla regresyon kontrolünden sonra değiştirilmelidir.

**İkinci RED/GREEN onarımı:** Testler, iki uydurma ama eşit logZ/hata değerinin önce yanlışlıkla kabul edilebildiğini ve README dosyasının gerçekten yeniden okunup okunmadığının belirtilmediğini gösterdi. Şimdi özgün logZ ve hata değerleri de sabit denetleniyor; isteğe bağlı gerçek README MD5 okumasının durumu raporda ayrı yazıyor. Sentetik testlerle toplam **10/10 PASS**.