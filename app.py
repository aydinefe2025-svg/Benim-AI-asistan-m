import logging
import os
import re
import requests
from urllib.parse import urlencode
import streamlit as st

# 📺 Rahat bir okuma için standart geniş ekran düzeni aktif ediliyor
st.set_page_config(layout="wide")

# 🔒 Her sağlayıcı bağımsız yapılandırılır. Değerleri hiçbir zaman ekranda gösterme.
from core.provider_config import (
    available_providers,
    configured_credentials,
    credential_presence,
)
from core.groq_diagnostics import check_groq_connection
from core.user_memory import export_library, import_library, memory_context, new_memory

_credentials = configured_credentials(st.secrets, os.environ)
_credential_presence = credential_presence(_credentials)
logging.getLogger(__name__).info(
    "Provider credential presence: GROQ_API_KEY=%s GOOGLE_API_KEY=%s",
    _credential_presence["GROQ_API_KEY"],
    _credential_presence["GOOGLE_API_KEY"],
)
available_models = available_providers(_credentials)
if not available_models:
    st.error("Model bağlantısı için GROQ_API_KEY veya GOOGLE_API_KEY gerekli. Render ortam değişkenlerini veya Streamlit Secrets ayarlarını kontrol edin.")
    st.stop()

GOOGLE_KEY = _credentials.get("GOOGLE_API_KEY")
GROQ_KEY = _credentials.get("GROQ_API_KEY")

# 🌐 ENGELSİZ CANLI İNTERNET VE METEOROLOJİ MOTORU
def internette_ara(sorgu: str) -> str:
    try:
        sorgu_temiz = sorgu.lower()
        
        # Kelime bazlı tam eşleşme kontrolü ile gereksiz tetiklenmeler önleniyor
        hava_istegi_mi = any(re.search(rf"\b{kelime}\b", sorgu_temiz) for kelime in ["hava", "derece", "sicak", "yagis", "rüzgar", "bulut", "güneş", "durumu"])
        
        if hava_istegi_mi:
            # Never silently assume a city: that would supply incorrect weather
            # for questions about another city (or with no city at all).
            city_pattern = r"([A-Za-zÇĞİÖŞÜçğıöşü]+)(?:['’](?:da|de|ta|te))?\s+hava\b"
            city_match = re.search(city_pattern, sorgu, flags=re.IGNORECASE)
            if city_match is None:
                city_match = re.search(
                    r"\bhava(?:\s+durumu)?\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
                    sorgu, flags=re.IGNORECASE,
                )
            city_name = city_match.group(1) if city_match else ""
            non_cities = {"bugün", "yarın", "şimdi", "dışarıda", "burada",
                          "nasıl", "kaç", "ne", "bizim", "bu"}
            if not city_name or city_name.casefold() in non_cities:
                return "Hava durumu için şehir belirtin; konum tahmin edilmiyor."
            sehir_adi = city_name.capitalize()
            sehir = city_name.translate(str.maketrans({
                "İ": "I", "ı": "i", "Ş": "S", "ş": "s", "Ç": "C", "ç": "c",
                "Ğ": "G", "ğ": "g", "Ö": "O", "ö": "o", "Ü": "U", "ü": "u",
            }))
            
            headers = {"Accept-Language": "tr", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = f"https://wttr.in/{sehir}?format=%C+%t+%h+%w"
            response = requests.get(url, headers=headers, timeout=6)
            
            if response.status_code == 200 and "error" not in response.text.lower():
                ham_veri = response.text.strip().split()
                if len(ham_veri) >= 3:
                    durum = ham_veri[0]
                    sicaklik = ham_veri[1]
                    nem = ham_veri[2]
                    ruzgar = ham_veri[3] if len(ham_veri) > 3 else "Hafif"
                    return f"HAVA SERVİSİ BİLGİSİ -> Şehir: {sehir_adi} | Durum: {durum} | Sıcaklık: {sicaklik} | Nem: {nem} | Rüzgar: {ruzgar}."
            return "Hava servisi şu anda güvenilir bilgi sunamıyor; güncel hava durumu doğrulanamadı."
                    
        # Diğer genel internet aramaları için standart API bağlantısı
        url = "https://api.duckduckgo.com/?" + urlencode({"q": sorgu, "format": "json", "no_html": 1})
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=6)
        if response.status_code == 200:
            data = response.json()
            if data.get("AbstractText"):
                return "DuckDuckGo anlık yanıt: " + str(data["AbstractText"])
                
        return "DuckDuckGo anlık yanıtında sonuç bulunamadı; bu tam web araması değildir."
    except Exception:
        return "İnternet veri kaynağına erişilemedi; güncel bilgi doğrulanamadı."

# 🎛️ SIDEBAR (YAN MENÜ) AYARLARI
st.sidebar.title("🤖 Asistan Kontrol Paneli")
secilen_model = st.sidebar.selectbox(
    "Kullanılacak Yapay Zeka Beyni:",
    available_models
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

# Explicit, read-only provider check. This lists models and never generates text.
if "Groq" in secilen_model and GROQ_KEY and st.sidebar.button("Groq bağlantısını doğrula"):
    check = check_groq_connection(GROQ_KEY, aktif_llm_adi)
    if check["reachable"] and check["model_available"]:
        st.sidebar.success("Groq bağlantısı ve seçili modele erişim doğrulandı; metin üretilmedi.")
    elif check["reachable"]:
        st.sidebar.warning("Groq API anahtarı kabul edildi, ancak seçili model listede görünmüyor.")
    else:
        st.sidebar.error("Groq bağlantısı doğrulanamadı. Ayrıntılar güvenlik için gizlendi.")

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

# 💬 SOHBET GEÇMİŞİ VE KULLANICI DENETİMLİ HAFIZA
if "messages" not in st.session_state:
    st.session_state.messages = []
if "saved_memories" not in st.session_state:
    st.session_state.saved_memories = []

with st.sidebar.expander("🧠 Hafıza kitaplığım", expanded=False):
    st.caption(
        "Yalnızca açıkça eklediğiniz notlar sonraki yanıtlara bağlam olur. "
        "Bu, modelin eğitildiği anlamına gelmez. Notlar oturumda tutulur; "
        "kalıcı saklamak için JSON olarak indirin ve sonraki oturumda içe aktarın. "
        "Gizli anahtar veya hassas kişisel bilgi kaydetmeyin."
    )
    memory_upload = st.file_uploader(
        "Kitaplık dosyasını seçin", type=["json"], key="memory_library_upload"
    )
    if st.button("Kitaplığı içe aktar", key="import_memory_library"):
        if memory_upload is None:
            st.warning("Önce JSON kitaplık dosyasını seçin.")
        else:
            try:
                st.session_state.saved_memories = import_library(memory_upload.getvalue())
                st.success(f"{len(st.session_state.saved_memories)} not içe aktarıldı.")
            except (ValueError, UnicodeError):
                st.error("Kitaplık dosyası geçersiz veya desteklenmiyor; içerik okunmadı.")

    st.download_button(
        "Hafıza kitaplığını indir",
        data=export_library(st.session_state.saved_memories),
        file_name="asistan-hafiza-kitapligi.json",
        mime="application/json",
        key="download_memory_library",
    )
    memory_text = st.text_area(
        "Açıkça saklamak istediğiniz not", max_chars=2000, key="memory_text_input"
    )
    memory_tags = st.text_input("Etiketler (virgülle ayırın)", key="memory_tags_input")
    if st.button("Notu hafızaya ekle", key="add_memory"):
        try:
            item = new_memory(
                memory_text, [tag.strip() for tag in memory_tags.split(",") if tag.strip()]
            )
            if len(st.session_state.saved_memories) >= 200:
                st.warning("Kitaplık en fazla 200 not tutabilir.")
            else:
                st.session_state.saved_memories.append(item)
                st.success("Not bu oturumun kitaplığına eklendi.")
        except ValueError:
            st.warning("Kaydetmek için 1–2000 karakter arasında bir not yazın.")

    if st.session_state.saved_memories:
        st.caption(f"Bu oturumda {len(st.session_state.saved_memories)} kayıtlı not var.")
        for index, item in enumerate(st.session_state.saved_memories):
            st.markdown(f"**{index + 1}.** {item['text']}")
            if st.button("Sil", key=f"delete_memory_{item['id']}"):
                st.session_state.saved_memories = [
                    saved for saved in st.session_state.saved_memories
                    if saved["id"] != item["id"]
                ]
                st.rerun()

# 🧠 Modeli Doğrudan Tetikleyen Arka Plan Sistemi
def asistani_calistir(kullanici_mesaji):
    arama_sonucu = internette_ara(kullanici_mesaji)
    
    saved_context = memory_context(st.session_state.saved_memories, kullanici_mesaji)
    sistem_talimati = f"""Sen sadece Türkçe konuşan, samimi ve harika bir dijital asistansın.
    İnternetten senin için gelen veri kutusu şudur: {arama_sonucu}
    {saved_context}
    
    🧠 KİMLİK BİLGİSİ:
    Bu, Python ve Streamlit ile geliştirilen bir asistan arayüzüdür. Yanıtlar seçilen harici Groq veya Google modeliyle üretilir. Kullanıcı sorarsa sağlayıcıyı doğru tanıt; yapımcı veya model kökeni hakkında doğrulanmamış iddialarda bulunma.
    
    ⚠️ SIKI KURALLAR:
    1. Yanıtının tamamı sadece doğal, akıcı ve kurallı bir Türkçe ile yazılmalıdır.
    2. Kullanıcıya doğrudan bir insan gibi samimi cevap ver, asla yarım bırakma.
    3. Eğer yukarıdaki veri kutusunda 'HAVA SERVİSİ BİLGİSİ' yazmıyorsa, hava durumundan KESİNLİKLE bahsetme. Kullanıcı sana ne sorduysa sadece ona odaklan ve normal bir şekilde sohbet et. Hava durumunu sadece kullanıcı açıkça sorduğunda ver."""

    try:
        raw_response = ""
        if "Groq" in secilen_model:
            api_mesajlari = [{"role": "system", "content": sistem_talimati}]
            for msg in st.session_state.messages:
                api_mesajlari.append({"role": msg["role"], "content": msg["content"]})
            # Chat UI already adds the current turn before invoking this
            # function. Append only for callers that have not done so.
            if not (api_mesajlari[-1]["role"] == "user" and
                    api_mesajlari[-1]["content"] == kullanici_mesaji):
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
        return "Model hizmetiyle bağlantı kurulamadı. Gizli yapılandırmayı kontrol edin."

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
