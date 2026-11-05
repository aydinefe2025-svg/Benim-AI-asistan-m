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
    natural_learning_request = (
        len(normalized) <= 240
        and any(phrase in normalized for phrase in self_learning_phrases)
        and not any(re.search(rf'\\b{re.escape(verb)}\\b', normalized) for verb in task_verbs)
    )
    if normalized not in exact_matches and not natural_learning_request:
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
