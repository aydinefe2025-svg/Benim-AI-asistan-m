# PSR J0740+6620 — 253–254 kabuk bölgesinde termodinamik ilk-yasa devamı

**Durum: Altı EOS için yalnız beş kaynak düğümünü kapsayan matematiksel aday doğrulandı. Bütün EOS, sürekli nedensellik veya dönen yıldız modeli onaylanmadı.**

## Ne hesaplandı?

Önceki kaynak-eşleşmiş altı modelin 253–254 enerji düğümüne yapılan koşullu, Öklid-minimum iki-nokta müdahalesi korunarak 252–256 arasındaki dört P–ε aralığında ε(P) parçalı doğrusal tanımlandı. Her aralıkta 0<dP/dε≤0,95 zorunlu tutuldu. Sonra **aynı tek ε(P)** üzerinden `dh=dP/(ε+P)` ve `dln n=dε/(ε+P)` analitik olarak entegre edildi. Sonuçlar bağımsız bileşik Simpson (512 alt-aralık/kenar) yöntemiyle kıyaslandı.

| EOS | Özgün negatif cs² düğümü | Maks. yerel ε müdahalesi | Yeni Δh / eski Δh - 1 | Parçalı-sekant + ilk yasa |
|---|---:|---:|---:|---|
| ENG | -0.1751758 | 0.016143% | +5.731277% | PASS |
| MPA1 | -0.1751745 | 0.016143% | +5.731278% | PASS |
| MS1 | -0.1751758 | 0.016143% | +5.731277% | PASS |
| MS1B | -0.1751745 | 0.016143% | +5.731278% | PASS |
| WFF1 | -0.1751745 | 0.016143% | +5.731278% | PASS |
| WFF2 | -0.1751745 | 0.016143% | +5.731278% | PASS |

## Neden fiziksel olarak önemli?

- Kaynak JESTER üretici kodu baryon yoğunluğunu yaklaşık `n=e/m_avg` olarak yazıyor. Bu, P>0 olduğunda soğuk maddenin `dε=(ε+P)dn/n` birinci yasasıyla genel olarak özdeş değil. Yeni yerel aday için **n(P) yeniden türetildi**; kaynak `n` veya `h` kopyalanmadı.
- Bu lokal parçada yeni entalpi artışı özgün h artışından **yaklaşık %5,7313 daha büyük**; fark yaklaşık **1,14994e-5** boyutsuz h. Bu fark farklı yerel e(P) temsili / interpolasyonu ile ilgilidir; tek başına orijinal X-PSI ya da LALSuite değerlerinin yanlış olduğunu kanıtlamaz.
- Termodinamik birinci-yasa tutarlılığı, **yeni seçilen parçalı-doğrusal varsayım altında matematiksel olarak** sağlandı. Gerçek sıfır-basınç yüzeyi, atom/çekirdek madde fiziği, 6 EOS native cs²<0, ENG/WFF merkez cs²>1 sorunları geçerli açık kapılardır.
- Bağımsız Simpson–analitik h testinde göreli hata tüm modellerde yaklaşık 1e-15 veya altında. 6 ayrı Python birim testi beklendiği şekilde kırmızıdan yeşile geçti; kaynak bilimsel tablo değiştirilmedi.

## Çıktı ve yeniden üretim

- `thermo_consistency_local.py`: üç fiziksel özdeşliği kullanan fail-closed yerel integral.
- `test_thermo_consistency_local.py`: 6 davranış testi (6 EOS alt testi, negatif orijinal ve geçersiz girdi retleri).
- `run_thermo_consistency_audit.py`: fikstürden tekrar JSON/MD üretir.
- `J0740_LOCAL_THERMODYNAMIC_CONSISTENCY_20261116.json`: tüm aday düğümler, entalpi, bağıl baryon yoğunluğu, kaynak ve yeni kontrol sayıları.
- Kaynak kimliği `c1e2e776d1c0032756e7aac8dda1022d698721748133610d798ada0a353c8412`, JESTER commit `e6768650ce992abfd1153a6833857572fe5cd230`.
- İşletme sınırı: **bu dosyalar nihai nükleer EOS tablosu, M–R kestirimi veya Bayes faktörü değildir**.

## Sıradaki kritik fizik işleri

1. Orijinal kaynak LALSuite EOS kabuğunun 253→254 geçişinin özgün fiziksel/interpolasyon mekanizması ve gerçek P→0 eşlemesi.
2. Tüm yüksek yoğunluk aralığında `0<c_s²/c²≤1`, monotoni ve EOS/entalpi/baryon ilişkisinin tek modelde ve gerçek kaynakla doğru uygulanması.
3. Yalnız bu fizik kapılarını geçen ayrı tanımlı adaylara bağımsız TOV-Love ve aynı kütle/dönme RNS GR doğrulaması.
4. Gerçek X-PSI nuisance bütünleştirmesi ve normalizasyon yapılmadan EOS kanıtı ilan edilmemesi.
