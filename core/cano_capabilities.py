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
        'Bu oturumda hafıza kitaplığın hesap sahibine bağlı PostgreSQL üzerinde açık; '
        'kaydettiğin bilgi sonraki oturumlarda da kullanılabilir.'
        if persistent_memory else
        'Bu oturumda hafıza kitaplığı tarayıcı deposunu kullanıyor; kalıcı büyüme için '
        'hesap bağlantılı depolama gerekir.'
    )
    colony = (
        'Ekip ve görev kayıtları için hesap sahibine bağlı PostgreSQL yedeği yapılandırılmış.'
        if persistent_colony else
        'Ekip kayıtları şu an oturumun SQLite dosyasında; JSON yedeğiyle koruyabilirsin.'
    )
    growth = (
        'Evet—hedefimiz CANO’nun bilgisini, uzman ekibini ve araştırma kapasitesini '
        'adım adım büyütmek. Uygulamadaki büyüme döngüsü şöyle:\n\n'
        '1. **Hedef belirle:** Komuta Merkezi görev alanına araştırma ya da geliştirme hedefini yaz.\n'
        '2. **Uzmanları çoğalt:** CANO ekibini hazırla; farklı uzman rolleri aynı hedefi kendi bakış açılarından işler.\n'
        '3. **Bir çevrimi tamamla:** Ekip görevi planlama, araştırma, eleştiri ve sonuç aşamalarından geçirir.\n'
        '4. **Bilgiyi biriktir:** Kaynakları ve sonuçları gözden geçir; işe yarayan dersi Öğrenen Uzman Ajanlar bölümünde kaydet ve onayla. '
        'Onaylı dersler sonraki uygun görevlerde bağlam olur.\n'
        '5. **Yeni turda genişlet:** Hafıza ve görev kayıtları, mevcut kurulumda sonraki çalışmalara taşınır.\n\n'
        + memory + ' ' + colony + '\n\n'
        'Hemen başlamak için Komuta Merkezi’ne tek bir somut hedef girip “Ekibi çalıştır — 4 aşama” düğmesine basabilirsin. '
        'Organizmalar Laboratuvarı hedeflerinde de simülasyon sorusunu, değişkenleri ve ölçütü açıkça yaz; '
        'çıktıyı yeni turda iyileştirmek üzere kaydedelim.\n\n'
        'Böylece sistemin bilgi tabanı ve görevlerde kullanabildiği uzman bağlamı büyür. '
        'Bu, temel modelin kendi ağırlıklarını otomatik eğitmesi anlamına gelmez; fiziksel deney yerine dijital simülasyon ve kanıt incelemesi yürütürüz.'
    )
    if general_capability_request:
        return growth
    return (
        growth + '\n\n'
        'Yani “öğrenme”, senin onayladığın dersleri ve kaydedilen araştırma sonuçlarını '
        'sonraki işlerde kullanarak adım adım gelişme demek. Bu açıklama yeni görev başlatmaz; '
        'birlikte başlatmak için yukarıdaki Komuta Merkezi akışını kullan.'
    )
