"""Describe application capabilities from runtime facts, without model guessing."""
import re


def capability_reply(message, *, persistent_memory=False, persistent_colony=False):
    normalized = ' '.join(str(message).casefold().replace('i\u0307', 'i').split())
    normalized = re.sub(r'[.!?,;]+$', '', normalized)
    exact_matches = {
        'kendini geliştir', 'kendini geliştir cano', 'cano kendini geliştir',
        'kendini geliştirebilir misin', 'kendini geliştirebilir misin cano',
        'hafızan var mı', 'hafızan var mı cano',
    }
    capability_questions = {
        'ne yapabilirsin', 'ne yapabilirsin cano', 'cano ne yapabilirsin',
        'neler yapabilirsin', 'neler yapabilirsin cano', 'cano neler yapabilirsin',
        'ne işler yapabilirsin', 'ne işler yapabilirsin cano',
        'hangi işleri yapabilirsin', 'hangi işleri yapabilirsin cano',
        'neler yaparsın', 'neler yaparsın cano', 'ne iş yaparsın',
        'yeteneklerin neler', 'özelliklerin neler',
    }
    # Accept natural self-learning questions/statements without routing actual
    # build or research requests away from their normal handlers.
    self_learning_phrases = (
        'bilgi toplayarak kendini geliştir',
        'bilgi toplayıp kendini geliştir',
        'kendini geliştirebilir miyiz',
        'kendi kendini geliştirebilir',
        'kendini öğrenerek geliştir',
        'deney yapmadan kendini geliştir',
        'fiziksel laboratuvar olmadan',
    )
    task_verbs = (
        'tasarla', 'kur', 'kodla', 'yaz', 'üret', 'araştır',
        'simüle et', 'başlat', 'oluştur',
    )
    contains_task = any(
        re.search(rf'\b{re.escape(verb)}\b', normalized) for verb in task_verbs
    )
    natural_learning_request = (
        len(normalized) <= 240
        and any(phrase in normalized for phrase in self_learning_phrases)
        and not contains_task
    )
    general_capability_request = normalized in capability_questions
    if (normalized not in exact_matches and not natural_learning_request
            and not general_capability_request):
        return None
    memory = (
        'Hafıza kitaplığın bu oturumda giriş hesabına bağlı PostgreSQL üzerinden açık.'
        if persistent_memory else
        'Hafıza kitaplığın bu oturumda tarayıcı deposunu kullanıyor; hesaplar ve cihazlar arasında eşitlenmiyor.'
    )
    colony = (
        'Ekip ve görev kayıtları için hesaba bağlı PostgreSQL yedeği yapılandırılmış. '
        'Ekranda eski yedeğin bulunduğu bildiriliyorsa önce “Kalıcı yedekten boş koloniyi geri yükle” düğmesini kullan.'
        if persistent_colony else
        'Ekip kayıtları bu oturumun SQLite dosyasında; kalıcı hesap yedeği bağlı değil. JSON yedeği al.'
    )
    if general_capability_request:
        return (
            'Evet, bu uygulamada sohbet etmenin yanında görev ve araştırma iş akışlarını da kullanabilirsin. '
            'Şu anda yapabildiklerim:\n\n'
            '- Soruları açıklamak, metinleri özetlemek ve bir hedefi uygulanabilir adımlara dönüştürmek.\n'
            '- Komuta Merkezi üzerinden uzman ajanlarla görev taslağı hazırlamak; iş akışı planlama, araştırma, eleştiri ve sonuç aşamalarından geçer. '
            'Üretilen sonuçlar kanıt ve kaynak açısından ayrıca incelenmelidir.\n'
            '- Uzman ajanlara verdiğin geri bildirimi ders olarak kaydetmek. Onayladığın dersler, uygun olduğunda sonraki görevlerde bağlam olarak kullanılır.\n'
            '- Açıkça kaydettiğin bilgileri hafıza kitaplığında sonraki oturumlarda kullanmak.\n\n'
            + memory + '\n\n' + colony + '\n\n'
            'Sınırlarım: fiziksel deney yapamam, kendi kendime arka planda kesintisiz araştırma çalıştıramam, '
            'takvim veya hatırlatıcı oluşturamam. Kaydedilen dersler modelin ağırlıklarını eğitmez; '
            'araştırma çıktıları doğrulanmış keşif değil, incelenmesi gereken aday bulgulardır.'
        )
    return (
        'CANO’da gelişim, onayladığın dersleri sonraki görevlere katmak ve sonuçları '
        'ölçmek üzerinden ilerliyor. Mevcut araçlarım:\n\n'
        '- **Öğrenen uzman ajanlar:** Kanıt referansıyla eklediğin ve onayladığın dersler '
        'seçili uzmanın sonraki görevlerine bağlam olur.\n'
        '- **Komuta Merkezi:** Ekip bir görevi planlama, araştırma, eleştiri ve sonuç '
        'aşamalarında işler; çıktılar ayrıca doğrulanmalıdır.\n'
        '- **Hafıza kitaplığı:** Açıkça kaydettiğin notlar sonraki yanıtlarda kullanılır.\n\n'
        + memory + '\n\n' + colony + '\n\n'
        'Bu mekanizma model ağırlıklarını yeniden eğitmez. Uygulama kodunu değiştirme '
        've yeni sürümü yayımlama işi Codex geliştirme akışında yapılır. '
        'Bu mesaj mevcut yetenekleri bildirir; yeni bir eğitim veya kod yayını başlatmaz.'
    )
