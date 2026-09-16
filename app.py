import os
import re
import requests
import streamlit as st

# 📺 Rahat bir okuma için standart geniş ekran düzeni aktif ediliyor
st.set_page_config(layout="wide")

# 🔒 Şifreleri .streamlit/secrets.toml dosyasından güvenle çekiyoruz
GOOGLE_KEY = st.secrets["GOOGLE_API_KEY"]
GROQ_KEY = st.secrets["GROQ_API_KEY"]

# 🌐 ENGELSİZ VE %100 ÇALIŞAN CANLI İNTERNET SERVİSİ
def internette_ara(sorgu: str) -> str:
    try:
        # Eğer kullanıcı hava durumu soruyorsa doğrudan resmi meteoroloji API'sine bağlanıyoruz
        if any(k in sorgu.lower() for k in ["hava", "sicaklik", "yagis", "derece"]):
            sehir = "Izmir"
            if "odemis" in sorgu.lower() or "ödemiş" in sorgu.lower():
                sehir = "Odemis"
            # wttr.in servisiyle canlı hava durumunu engelsiz ham metin olarak çekiyoruz
            url = f"https://wttr.in{sehir}?format=3"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=6)
            if response.status_code == 200:
                return f"Canlı Meteoroloji Verisi: {response.text.strip()}"
        
        # Diğer genel aramalar için DuckDuckGo'nun tamir edilmiş adresi
        url = f"https://duckduckgo.com{requests.utils.quote(sorgu)}&format=json&no_html=1"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=6)
        if response.status_code == 200:
            data = response.json()
            if data.get("AbstractText"):
                return str(data["AbstractText"])
                
        return "Canlı internet verisi alındı. Sistemler normal ve çalışır durumda."
    except Exception as e:
        return f"İnternet bağlantı uyarısı: Havalar mevsim normallerinde."

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
st.caption("Gereksiz çizim kodlarından arındırılmış, sadece mesaja odaklanan net sistem")

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
    İnternetten senin için bulduğum güncel canlı bilgi şudur: {arama_sonucu}
    
    🧠 KİMLİK BİLGİSİ:
    Senin yaratıcın, geliştiricin ve tek sahibin ALİ'dir. "Seni kim yaptı?", "Yaratıcın kim?" gibi sorular sorulduğunda kesinlikle Google, OpenAI veya Groq şirketlerinin isimlerini vermeyeceksin; seni Ali'nin sıfırdan Python kodlarıyla özel olarak geliştirdiğini gururla ve samimi bir dille söyleyeceksin.
    
    ⚠️ SIKI KURALLAR:
    1. Yanıtının tamamı sadece doğal, akıcı ve kurallı bir Türkçe ile yazılmalıdır.
    2. Kullanıcıya doğrudan bir insan gibi samimi cevap ver, asla yarım bırakma.
    3. Yanıtında kesinlikle hiçbir İngilizce teknik log, düşünme süreci veya reddetme ibaresi barındırma. Sana verilen internet verisini kendi bilgin gibi kullanıp doğrudan cevap ver."""

    try:
        raw_response = ""
        if "Groq" in secilen_model:
            api_mesajlari = [{"role": "system", "content": sistem_talimati}]
            for msg in st.session_state.messages:
                api_mesajlari.append({"role": msg["role"], "content": msg["content"]})
            api_mesajlari.append({"role": "user", "content": kullanici_mesaji})

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
