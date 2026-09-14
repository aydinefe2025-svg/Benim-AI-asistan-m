import os
import re
import requests
from google import genai
from google.genai import types
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
# 🔒 Gizli dosyayı okumak için kütüphaneyi ekledik:
from dotenv import load_dotenv

# .env dosyasındaki gizli şifreleri bilgisayarın hafızasına yüklüyoruz
load_dotenv()

# 🔑 Şifreleri doğrudan gizli kutudan (hafızadan) çekiyoruz
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")

# 🌐 Engelsiz Canlı İnternet Arama Fonksiyonu
def internette_ara(sorgu: str) -> str:
    try:
        url = "https://duckduckgo.com"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        payload = {'q': sorgu}
        response = requests.post(url, headers=headers, data=payload, timeout=8)
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            metinler = [td.get_text(strip=True) for td in soup.find_all("td", class_="result-snippet")[:3]]
            if metinler:
                return "\n".join(metinler)
        return "Arama sonucuna ulaşılamadı, genel bilgilerinle yanıtla."
    except:
        return "Arama bağlantı hatası."

# 🧠 Yapay Zekayı Çalıştıran Ana Fonksiyon
def yapay_zeka_yaniti(kullanici_mesaji):
    arama_sonucu = internette_ara(kullanici_mesaji)
    
    sistem_talimati = f"""Sen sadece Türkçe konuşan, samimi ve harika bir Telegram asistanısın. 
    İnternetten senin için bulduğum güncel canlı bilgi şudur: {arama_sonucu}
    
    🧠 KİMLİK BİLGİSİ:
    Senin yaratıcın, geliştiricin ve tek sahibin ALİ'dir. "Seni kim yaptı?", "Yaratıcın kim?", "Geliştiricin kim?" gibi sorular sorulduğunda kesinlikle Google, OpenAI veya Groq şirketlerinin isimlerini vermeyeceksin; seni Ali'nin sıfırdan Python kodlarıyla özel olarak geliştirdiğini gururla ve samimi bir dille söyleyeceksin.
    
    ⚠️ SIKI KURALLAR:
    1. Yanıtının tamamı sadece doğal, akıcı ve kurallı bir Türkçe ile yazılmalıdır.
    2. Kullanıcıya doğrudan bir insan gibi samimi cevap ver, asla yarım bırakma.
    3. Yanıtında kesinlikle hiçbir İngilizce teknik log veya düşünme süreci barındırma."""

    try:
        client = Groq(api_key=GROQ_KEY)
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": sistem_talimati},
                {"role": "user", "content": kullanici_mesaji}
            ],
            max_tokens=1000
        )
        raw_response = completion.choices.message.content
        temiz_cevap = re.sub(r'<(think|thought|düşün).*?(</\1>|$)', '', raw_response, flags=re.DOTALL | re.IGNORECASE)
        return temiz_cevap.strip()
    except Exception as e:
        return f"Ufak bir teknik sorun oluştu, lütfen tekrar dener misin? Hata: {str(e)}"

# 🚀 Telegram Komut ve Mesaj Yakalayıcıları
async def start_komutu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Merhaba! Ben senin otonom yapay zeka asistanınım. Beni sıfırdan geliştiren Ali'ye selam olsun! Bana internetten araştırmak istediğin her şeyi sorabilirsin!")

async def mesaj_geldi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_mesaji = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    cevap = yapay_zeka_yaniti(kullanici_mesaji)
    await update.message.reply_text(cevap)

# 🏁 Botu Başlatan Ana Kod
def main():
    print("🚀 Telegram Botu arka planda başlatılıyor...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_komutu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_geldi))
    
    print("✅ Bot şu an aktif! Telefonunuzdan Telegram'a girip mesaj atabilirsiniz.")
    app.run_polling()

if __name__ == '__main__':
    main()
