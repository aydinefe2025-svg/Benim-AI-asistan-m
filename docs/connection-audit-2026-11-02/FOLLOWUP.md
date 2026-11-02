# Kalan eksiklerin giderilmesi

## Giderilenler ve gerçek doğrulama

- **OpenCode → Ollama → qwen3:8b:** mevcut OpenCode v2.2.3 üzerinden
  `run --model ollama/qwen3:8b --format json` çalıştırıldı. Araç çağrısı
  yapmaması ve yalnızca `CODEX_LOCAL_OK` döndürmesi istendi. Beklenen metin
  alındı, süreç exit 0, bildirilen maliyet 0. Mevcut kurulum korundu.
- **Canlı Groq:** Render uygulamasındaki “Groq bağlantısını doğrula” düğmesi
  “Groq bağlantısı ve seçili modele erişim doğrulandı; metin üretilmedi”
  sonucunu verdi. Bulut çıkarımı veya ücretli model isteği yapılmadı.
- **MuJoCo:** mevcut `research/mujoco-ci-issue-23` dalındaki dört doğrulama
  betiği ve CI iş akışı bu dala koruyarak taşındı. MuJoCo 3.17.0 ayrı
  `requirements-robotics.txt` içinde sabitlendi; sohbet uygulamasının
  bağımlılıklarına eklenmedi. Başarılı gerçek motor sonuçları `physics/`
  altında SHA-256 dosyalarıyla kayıtlıdır. Kaynak dal diğer değişiklikleriyle
  birleştirilmedi; nötron yıldızı araştırmasına dokunulmadı.
- **Fizik sonuçları:** serbest düşüş hatası yaklaşık 0.004905 m (eşik 0.02 m);
  seri/batch konum farkı 0; temas deneyi 2572 temas adımı ve son yükseklik
  0.099633 m (beklenen 0.1 ± 0.03 m). Tekrarlı benchmark 7 tekrar; ölçümler
  bu makine ve bu modele aittir, genel hızlanma garantisi değildir.
- **Google/Telegram denetimi:** `scripts/check_connections.py` yalnızca
  Groq/Google model-listesi ve Telegram `getMe` çağırır. Anahtarları veya
  sağlayıcı hata metnini yazdırmaz; mesaj, polling veya metin üretimi yapmaz.
  Eksik kimlik bilgisi exit 1 ve `not_configured` üretir. Google için uygulamaya
  ayrı salt okunur doğrulama düğmesi ve `GOOGLE_MODEL` ortam ayarı eklendi.
- **Tam SQLite yedeği:** `scripts/sqlite_snapshot.py` tek dizindeki `.sqlite3`
  ve `.db` dosyalarını SQLite online backup API ile yeni bir dizine alır.
  Oturum görevleri, geçmiş ve taslaklar dahil tüm tablolar korunur. SHA-256
  ve SQLite bütünlüğü geri yükleme öncesi kontrol edilir. Dosya üzerine yazılmaz,
  eski veriler silinmez, dış ağa aktarım yapılmaz. WAL'de commit edilmiş veri
  de gerçek açık bağlantıyla test edildi. Her veritabanı kendi içinde tutarlıdır;
  farklı dosyalar için ortak tek transaction garantisi yoktur.

## Yeniden çalıştırma

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-bot.txt
.venv/Scripts/python.exe -m pip install -r requirements-robotics.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/check_connections.py
.venv/Scripts/python.exe research_ci/mujoco_smoke.py
.venv/Scripts/python.exe research_ci/mujoco_batch.py
.venv/Scripts/python.exe research_ci/mujoco_contact.py
.venv/Scripts/python.exe research_ci/mujoco_benchmark.py
.venv/Scripts/python.exe scripts/sqlite_snapshot.py backup data private-backups/new-snapshot
.venv/Scripts/python.exe scripts/sqlite_snapshot.py restore private-backups/new-snapshot private-backups/new-recovery
```

Yedek ve geri yükleme hedefleri yeni dizinler olmalıdır. Bu dosyaları GitHub'a
yüklemeyin; gerçek kişisel veriler içerebilirler. Yalnızca hash ve aynı yerde
tutulan manifest, saldırgana karşı özgünlük kanıtı değildir; güvenilir ayrı bir
kopya saklayın. Başarısız bir işlem kısmi yeni hedef bırakabilir; başarılı
manifest yoksa yedek tamamlandı sayılmaz. Kaynak dosyalar değiştirilmez.

## Giderilmesi için dış bilgi gereken engeller

1. **Google/Telegram kimlik bilgileri:** bu çalışma ortamında ilgili ortam
   değişkenleri ve proje gizli dosyaları yok. Kody'de Groq adına kullanılabilir
   secret kaydı bulunmadı. Canlı uygulamanın sağlayıcı menüsünde yalnızca Groq
   var. Bu servisler için gerçek anahtar olmadan başarılı canlı doğrulama
   yapılamaz; değerler sohbete istenmedi ve uydurulmadı.
2. **Render kalıcı verisi ve canlı güncelleme:** servis `free` planında, otomatik
   dağıtımı kapalı. Mevcut bağlı Neon ve Supabase hesaplarında proje yok.
   Render'ın resmi belgelerine göre ücretsiz web servisinde kalıcı disk ve
   SSH/shell erişimi yok; yeniden başlatma/dağıtım geçici dosyaları kaybettirebilir.
   Kullanıcının “mevcut verileri silme” kuralını korumak için canlı servis
   yeniden dağıtılmadı. Güvenli biçimde alınmış mevcut verinin yedeği veya
   halihazırda kullanılan kalıcı depo kaynağı gereklidir. Yeni ücretli servis
   oluşturulmadı; yeni hesap açılmadı.
3. **Fiziksel robot:** cihaz ve bağlantı adresi verilmedi. Grid veri
   doğrulayıcıları ve gerçek MuJoCo motoru test edildi; bunlar donanım bağlantısı
   kanıtı değildir. Kullanıcıya donanım mı yalnızca simülasyon mu istendiği soruldu.

Bu engeller sessizce “çözüldü” durumuna çevrilmedi. Kod ve test değişiklikleri
PR #51 üzerinde izlenebilir; yayın kararı veri korunumu engelinden ayrıdır.

Resmi başvurular:
- https://render.com/docs/free
- https://render.com/docs/ssh
- https://ai.google.dev/api/models
- https://core.telegram.org/bots/api#getme
