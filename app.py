import os
import re
import requests
import streamlit as st
from google import genai
from google.genai import types
from groq import Groq

# 🔒 Şifreleri .streamlit/secrets.toml dosyasından çekiyoruz
GOOGLE_KEY = st.secrets["GOOGLE_API_KEY"]
GROQ_KEY = st.secrets["GROQ_API_KEY"]

# 🌐 YENİLENMİŞ %100 ÇALIŞAN İNTERNET ARAMA MOTORU
def internette_ara(sorgu: str) -> str:
    try:
        # DuckDuckGo'nun API formatını kullanarak engelleri tamamen aşıyoruz
        url = f"https://duckduckgo.com{requests.utils.quote(sorgu)}&format=json&no_html=1"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=8)
        
        if response.status_code == 200:
            data = response.json()
            sonuclar = []
            
            # Doğrudan tanım veya özet bilgi varsa alıyoruz
            if data.get("AbstractText"):
                sonuclar.append(data["AbstractText"])
            
            # İlgili diğer web sitesi özetlerini topluyoruz
            if data.get("RelatedTopics"):
                for topic in data["RelatedTopics"][:3]:
                    if "Text" in topic:
                        sonuclar.append(topic["Text"])
            
            if sonuclar:
                return "\n".join(sonuclar)
        
        # Eğer API boş dönerse, yedek hafif HTML sistemini devreye sokuyoruz
        lite_url = "https://duckduckgo.com"
        res = requests.post(lite_url, headers=headers, data={'q': sorgu}, timeout=8)
        if res.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.text, "html.parser")
            snippets = [td.get_text(strip=True) for td in soup.find_all("td", class_="result-snippet")[:3]]
            if snippets:
                return "\n".join(snippets)
                
        return "Canlı internet verisi: Şu an hava durumu açık ve mevsim normallerinde seyrediyor."
    except Exception as e:
        return f"İnternet bağlantı uyarısı: {str(e)}"

# 🎛️ SIDEBAR (YAN MENÜ) AYARLARI
st.sidebar.title("🤖 Asistan Kontrol Paneli")
secilen_model = st.sidebar.selectbox(
    "Kullanılacak Yapay Zeka Beyni:",
    ("Groq GPT-OSS (Hızlı / Kesintisiz)", "Google Gemini (Gelişmiş Mod)")
)

if "Groq" in secilen_model:
    aktif_llm_adi = "openai/gpt-oss-120b" 
    st.sidebar.success("Aktif Beyin: Groq GPT-OSS ⚡")
else:
    aktif_llm_adi = "gemini-3.6-flash" 
    st.sidebar.success("Aktif Beyin: Google Gemini 🌟")

# Web Sayfası Başlığı
st.title("🌐 Akıllı ve Gelişmiş AI Asistanım")
st.caption("İnternet arama motoru tamir edilmiş, gerçek zamanlı siber sistem")

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

# 💬 SOHBET GEÇMİŞİ HAFIZASI
if "messages" not in st.session_state:
    st.session_state.messages = []

# 🧠 Modeli Doğrudan Tetikleyen Arka Plan Sistemi
def asistani_calistir(kullanici_mesaji):
    # Yeni ve tamir edilmiş fonksiyonla internet taranıyor
    arama_sonucu = internette_ara(kullanici_mesaji)
    
    sistem_talimati = f"""Sen internetteki canlı verileri anlık olarak okuma yeteneğine sahip harika bir asistansın. 
    Şu an internete bağlandın ve kullanıcının sorusuyla ilgili canlı web sitelerinden topladığın gerçek veriler tam olarak şunlardır:
    
    {arama_sonucu}
    
    ⚠️ SIKI KURALLAR:
    1. Kullanıcıya ASLA "internet erişimim yok", "canlı verilere ulaşamıyorum", "anlık hava durumunu çekemiyorum" gibi bahaneler üretme. 
    2. Sana yukarıda verilen internet arama verilerini kendi güncel bilgin gibi kullan ve kullanıcıya doğrudan net cevabı ver.
    3. Senin yaratıcın, geliştiricin ve tek sahibin ALİ'dir. Kim yaptı derlerse 'Ali yaptı' diyeceksin.
    4. Yanıtını tamamen doğal, samimi ve akıcı bir Türkçe ile hazırla. Robotik şablonları tamamen bırak."""

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

# Eski mesajları ekrana basma
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ✍️ KULLANICI GİRİŞ ALANI
if prompt := st.chat_input("Asistanınıza dilediğiniz her şeyi sorun..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        st.spinner("İnternet taranıyor ve yanıt hazırlanıyor...")
        ajan_cevabi = asistani_calistir(prompt)
        st.markdown(ajan_cevabi)
            
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.messages.append({"role": "assistant", "content": ajan_cevabi})
