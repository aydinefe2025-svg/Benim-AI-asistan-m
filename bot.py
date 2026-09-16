import os
import re
import requests
from google import genai
from google.genai import types
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# 🔒 .env dosyasındaki gizli şifreleri bilgisayarın hafızasına yüklüyoruz
load_dotenv()

# 🔑 Şifreleri doğrudan gizli kutudan (hafızadan) çekiyoruz
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")

# 🌐 ENGELSİZ CANLI İNTERNET VE METEOROLOJİ MOTORU
def internette_ara(sorgu: str) -> str:
    try:
        sorgu_temiz = sorgu.lower()
        
        # Kelime bazlı tam eşleşme kontrolü ile gereksiz tetiklenmeler önleniyor
        hava_istegi_mi = any(re.search(rf"\b{kelime}\b", sorgu_temiz) for kelime in ["hava", "derece", "sicak", "yagis", "rüzgar", "bulut", "güneş", "durumu"])
        
        if hava_istegi_mi:
            sehir = "Izmir"
            sehir_adi = "İzmir"
            if "odemis" in sorgu_temiz or "ödemiş" in sorgu_temiz:
                sehir = "Odemis"
                sehir_adi = "Ödemiş"
                
            headers = {"Accept-Language": "tr", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = f"https://wttr.in{sehir}?format=%C+%t+%h+%w"
            response = requests.get(url, headers=headers, timeout=6)
            
            if response.status_code == 200 and "error" not in response.text.lower():
                ham_veri = response.text.strip().split()
                if len(ham_veri) >= 3:
                    durum = ham_veri[0]
                    sicaklik = ham_veri[1]
                    nem = ham_veri[2]
                    ruzgar = ham_veri[3] if len(ham_veri) > 3 else "Hafif"
                    return f"MÜHÜRLÜ UYDU RAPORU -> Şehir: {sehir_adi} | Durum: {durum} | Sıcaklık: {sicaklik} | Nem: {nem} | Rüzgar: {ruzgar}."
            return "Hava durumu uydusu şu an veri yeniliyor, genel iklim bilgisiyle Ali'ye yanıt ver."
                    
        # Diğer genel internet aramaları için standart API bağlantısı
        url = f"https://duckduckgo.com{requests.utils.quote(sorgu)}&format=json&no_html=1"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=6)
        if response.status_code == 200:
            data = response.json()
            if data.get("AbstractText"):
                return str(data["AbstractText"])
                
        return "Normal genel sohbet modu aktif. İnternet verisi aramaya gerek yok."
    except Exception as e:
        return "Sistem normal sohbet akışında kararlı durumda çalışıyor."

# 🧠 Yapay Zekayı Çalıştıran Ana Fonksiyon
def yapay_zeka_yaniti(kullanici_mesaji):
    arama_sonucu = internette_ara(kullanici_mesaji)
    
    sistem_talimati = f"""Sen sadece Türkçe konuşan, samimi ve harika bir Telegram asistanısın. 
    İnternetten senin için gelen veri kutusu şudur: {arama_sonucu}
    
    🧠 KİMLİK BİLGİSİ:
    Senin yaratıcın, geliştiricin ve tek sahibin ALİ'dir. "Seni kim yaptı?", "Yaratıcın kim?" gibi sorular sorulduğunda kesinlikle Google, OpenAI veya Groq şirketlerinin isimlerini vermeyeceksiniz; seni Ali'nin sıfırdan Python kodlarıyla özel olarak geliştirdiğini gururla ve samimi bir dille söyleyeceksin.
    
    ⚠️ SIKI KURALLAR:
    1. Yanıtının tamamı sadece doğal, akıcı ve kurallı bir Türkçe ile yazılmalıdır.
    2. Kullanıcıya doğrudan bir insan gibi samimi cevap ver, asla yarım bırakma.
    3. Eğer yukarıdaki veri kutusunda 'MÜHÜRLÜ UYDU RAPORU' yazmıyorsa, hava durumundan KESİNLİKLE bahsetme. Kullanıcı sana ne sorduysa sadece ona odaklan ve normal bir şekilde sohbet et. Hava durumunu sadece kullanıcı açıkça sorduğunda ver."""

    try:
        # Hızlı ve kesintisiz yanıt için Groq modelini tetikliyoruz
        client = Groq(api_key=GROQ_KEY)
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": sistem_talimati},
                {"role": "user", "content": kullanici_mesaji}
            ],
            max_tokens=1000
        )
        # 👑 HATA ÇÖZÜLDÜ: Liste indeksi [0] doğru şekilde mühürlendi
        raw_response = completion.choices[0].message.content
        temiz_cevap = re.sub(r'<(think|thought|düşün).*?(</\1>|$)', '', raw_response, flags=re.DOTALL | re.IGNORECASE)
        return temiz_cevap.strip()
    except Exception as e:
        return f"Ufak bir teknik sorun oluştu Ali, lütfen tekrar dener misin? Hata: {str(e)}"

# 🚀 Telegram Komut ve Mesaj Yakalayıcıları
async def start_komutu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Merhaba! Ben senin otonom yapay zeka asistanınım. Beni sıfırdan geliştiren Ali'ye selam olsun! Bana dilediğin her şeyi sorabilirsin!")

async def mesaj_geldi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_mesaji = update.message.text
    
    # Telefonunuza "Asistan yazıyor..." bildirimi gönderir
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Yapay zekadan yanıtı alıp Telegram'dan gönderiyoruz
    cevap = yapay_zeka_yaniti(kullanici_mesaji)
    await update.message.reply_text(cevap)

# 🏁 Botu Başlatan Ana Kod
def main():
    print("🚀 Telegram Botu arka planda başlatılıyor...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Komutları ve mesaj yakalayıcıları tanımlıyoruz
    app.add_handler(CommandHandler("start", start_komutu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_geldi))
    
    print("✅ Bot şu an aktif! Telefonunuzdan Telegram'a girip mesaj atabilirsiniz.")
    app.run_polling()

if __name__ == '__main__':
    main()
