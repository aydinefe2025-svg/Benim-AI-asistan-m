import os
import re
import requests
import streamlit as st

# 📺 Rahat bir okuma için standart geniş ekran düzeni aktif ediliyor
st.set_page_config(layout="wide")

# 🔒 Şifreleri .streamlit/secrets.toml dosyasından güvenle çekiyoruz
GOOGLE_KEY = st.secrets["GOOGLE_API_KEY"]
GROQ_KEY = st.secrets["GROQ_API_KEY"]

# 🌐 ENGELSİZ CANLI İNTERNET VE METEOROLOJİ MOTORU
def internette_ara(sorgu: str) -> str:
    try:
        # Türkçe karakterleri sadeleştir; "sıcaklık", "yağış" gibi ifadeler de eşleşsin.
        sorgu_temiz = sorgu.lower().translate(str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}))
        
        # Hava durumu yalnızca hava durumu terimleri açıkça geçince tetiklenir.
        hava_istegi_mi = any(re.search(rf"\b{kelime}\b", sorgu_temiz) for kelime in ["hava", "derece", "sicak", "sicaklik", "yagis", "ruzgar", "bulut", "gunes", "durumu", "nem"])
        
        if hava_istegi_mi:
            sehir = "Izmir"
            sehir_adi = "İzmir"
            if "odemis" in sorgu_temiz:
                sehir = "Odemis"
                sehir_adi = "Ödemiş"
                
            headers = {"Accept-Language": "tr", "User-Agent": "Mozilla/5.0"}
            url = f"https://wttr.in/{sehir}?format=j1"
            response = requests.get(url, headers=headers, timeout=8)
            
            if response.status_code == 200:
                weather = response.json()
                current = weather.get("current_condition", [{}])[0]
                desc = current.get("weatherDesc", [{}])[0].get("value", "Bilinmiyor")
                sicaklik = current.get("temp_C", "—") + "°C"
                nem = current.get("humidity", "—") + "%"
                ruzgar = current.get("windspeedKmph", "—") + " km/sa"
                return f"MÜHÜRLÜ UYDU RAPORU -> Şehir: {sehir_adi} | Durum: {desc} | Sıcaklık: {sicaklik} | Nem: {nem} | Rüzgar: {ruzgar}."
            return "Hava durumu servisi şu an veri vermiyor."
                    
        # Diğer genel internet aramaları için standart API bağlantısı
        # DuckDuckGo Instant Answer API; parametreleri requests güvenli biçimde kodlar.
        url = "https://api.duckduckgo.com/"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(
            url,
            params={"q": sorgu, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers=headers,
            timeout=8,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("AbstractText"):
                return str(data["AbstractText"])
                
        return "Normal genel sohbet modu aktif. İnternet verisi aramaya gerek yok."
    except Exception as e:
        return "Sistem normal sohbet akışında kararlı durumda çalışıyor."

# 🎛️ SIDEBAR (YAN MENÜ) AYARLARI
st.sidebar.title("🤖 Asistan Kontrol Paneli")
secilen_model = st.sidebar.selectbox(
    "Kullanılacak Yapay Zeka Beyni:",
    ("Groq GPT-OSS (Hızlı / Kesintisiz)", "Google Gemini (Gelişmiş Mod)")
)

if "Groq" in secilen_model:
    from groq import Groq
    aktif_llm_adi = "openai/gpt-oss-120b" 
    st.sidebar.success("Aktif Beyin: Groq GPT-OSS ⚡")
else:
    from google import genai
    from google.genai import types
    aktif_llm_adi = "gemini-3.6-flash" 
    st.sidebar.success("Aktif Beyin: Google Gemini 🌟")

# Web Sayfası Başlığı ve Sade Tasarım
st.title("🌐 Standart ve Kararlı AI Asistanım")
st.caption("Her mesajda hava durumuna atlama sorunu ve liste indeksi hatası düzeltilmiş kararlı asistan")

# 🎨 Tarayıcı düzeyinde <think> etiketlerini tamamen yok eden CSS kodu
st.markdown(
    """
    <style>
    think, .think, [class*="think"], .stChatMessage p:has(code) {
        display: none !important;
        visibility: hidden !important;
        height: 0px !important;
        margin: 0px !important;
        padding: 0px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 💬 SOHBET GEÇMİŞİ HAFIZASI (Session State)
if "messages" not in st.session_state:
    st.session_state.messages = []

# 🧠 Modeli Doğrudan Tetikleyen Arka Plan Sistemi
def asistani_calistir(kullanici_mesaji):
    arama_sonucu = internette_ara(kullanici_mesaji)
    
    sistem_talimati = f"""Sen sadece Türkçe konuşan, samimi ve harika bir dijital asistansın. 
    İnternetten senin için gelen veri kutusu şudur: {arama_sonucu}
    
    🧠 KİMLİK BİLGİSİ:
    Senin yaratıcın, geliştiricin ve tek sahibin ALİ'dir. "Seni kim yaptı?", "Yaratıcın kim?" gibi sorular sorulduğunda kesinlikle Google, OpenAI veya Groq şirketlerinin isimlerini vermeyeceksiniz; seni Ali'nin sıfırdan Python kodlarıyla özel olarak geliştirdiğini gururla ve samimi bir dille söyleyeceksin.
    
    ⚠️ SIKI KURALLAR:
    1. Yanıtının tamamı sadece doğal, akıcı ve kurallı bir Türkçe ile yazılmalıdır.
    2. Kullanıcıya doğrudan bir insan gibi samimi cevap ver, asla yarım bırakma.
    3. Eğer yukarıdaki veri kutusunda 'MÜHÜRLÜ UYDU RAPORU' yazmıyorsa, hava durumundan KESİNLİKLE bahsetme. Kullanıcı sana ne sorduysa sadece ona odaklan ve normal bir şekilde sohbet et. Hava durumunu sadece kullanıcı açıkça sorduğunda ver."""

    try:
        raw_response = ""
        if "Groq" in secilen_model:
            api_mesajlari = [{"role": "system", "content": sistem_talimati}]
            # Mevcut kullanıcı mesajı zaten session_state.messages içine eklendi.
            # Son mesajı tekrar eklememek için yalnızca önceki mesajları aktar.
            for msg in st.session_state.messages[:-1]:
                api_mesajlari.append({"role": msg["role"], "content": msg["content"]})

            client = Groq(api_key=GROQ_KEY)
            completion = client.chat.completions.create(
                model=aktif_llm_adi,
                messages=api_mesajlari,
                max_tokens=1000 
            )
            # 👑 HATA DÜZELTİLDİ: choices listesinin ilk elemanına [0] ile erişildi!
            raw_response = completion.choices[0].message.content
        else:
            client = genai.Client(api_key=GOOGLE_KEY)
            response = client.models.generate_content(
                model=aktif_llm_adi,
                contents=kullanici_mesaji,
                config=types.GenerateContentConfig(
                    system_instruction=sistem_talimati,
                    max_output_tokens=1000
                )
            )
            raw_response = response.text

        temiz_cevap = re.sub(r'<(think|thought|düşün).*?(</\1>|$)', '', raw_response, flags=re.DOTALL | re.IGNORECASE)
        return temiz_cevap.strip()

    except Exception as e:
        return f"Sistem yanıt verirken bir sorun oluştu. Hata: {str(e)}"

# 🔄 SOHBET AKIŞINI EKRANA BASMA (Temiz Hafıza Akışı)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ✍️ KULLANICI GİRİŞ ALANI
if prompt := st.chat_input("Asistanınıza dilediğiniz her şeyi sorun..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("assistant"):
        with st.spinner("Asistanınız yanıt hazırlıyor..."):
            ajan_cevabi = asistani_calistir(prompt)
            st.markdown(ajan_cevabi)
            
            st.session_state.messages.append({"role": "assistant", "content": ajan_cevabi})
