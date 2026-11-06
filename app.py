Warning: truncated output (original token count: 9865)
Total output lines: 716

import logging
import os
import re
from uuid import uuid4
import requests
from urllib.parse import urlencode
import streamlit as st

# 📺 Rahat bir okuma için standart geniş ekran düzeni aktif ediliyor
st.set_page_config(layout="wide")

# Optional fail-closed production login. Keep APP_AUTH_REQUIRED unset locally;
# enable it on Render only after the Google OIDC secrets file is configured.
from core.authentication import auth_is_required, render_auth_gate
from core.storage_config import cano_database_url, database_provider_label, memory_database_url

_AUTH_REQUIRED = auth_is_required(os.environ)
_OWNER_KEY = render_auth_gate(st, os.environ)
_MEMORY_STORE = None
_MEMORY_DATABASE_URL = memory_database_url(os.environ)
if _MEMORY_DATABASE_URL:
    if not _AUTH_REQUIRED or not _OWNER_KEY:
        st.error("Kalıcı kullanıcı verisi için doğrulanmış giriş zorunludur.")
        st.stop()
    try:
        from core.postgres_memory import PostgresMemoryStore
        _MEMORY_STORE = PostgresMemoryStore(database_url=_MEMORY_DATABASE_URL)
        _MEMORY_STORE.verify_schema()
    except Exception:
        st.error("Kalıcı hafıza bağlantısı kurulamadı; kayıtlar değiştirilmedi.")
        st.stop()

_TASK_STORE = None
if os.environ.get("AGENT_TASK_DATABASE_URL"):
    if not _AUTH_REQUIRED or not _OWNER_KEY:
        st.error("Kalıcı görev verisi için doğrulanmış giriş zorunludur.")
        st.stop()
    try:
        from core.postgres_task_store import PostgresTaskStore
        _TASK_STORE = PostgresTaskStore(owner_key=_OWNER_KEY)
        _TASK_STORE.verify_schema()
    except Exception:
        st.error("Kalıcı görev veritabanı bağlanamadı; görevler değiştirilmedi.")
        st.stop()


# 🔒 Her sağlayıcı bağımsız yapılandırılır. Değerleri hiçbir zaman ekranda gösterme.
from core.provider_config import (
    available_providers,
    configured_credentials,
    credential_presence,
)
from core.groq_diagnostics import check_groq_connection
from core.provider_failure import failure_category, safe_failure_message
from core.connection_diagnostics import check_provider
from core.public_research import research_sources
from core.scientific_sources import scientific_sources
from core.research_status import label_research_answer
from core.user_memory import export_library, import_library, memory_context, new_memory
from core.browser_memory import browser_memory_component, decode_snapshot, write_confirmed, explicit_memory_request
from core.task_panel import render_task_panel
from core.authorized_queue_panel import render_authorized_queue_panel
from core.colony_panel import render_colony_panel
from core.organism_lab_panel import render_organism_lab_panel
from core.cano_command_center import render_cano_command_center
from core.groq_team import generate_team_stage

_credentials = configured_credentials(st.secrets, os.environ)
_credential_presence = credential_presence(_credentials)
logging.getLogger(__name__).info(
    "Provider credential presence: GROQ_API_KEY=%s GOOGLE_API_KEY=%s",
    _credential_presence["GROQ_API_KEY"],
    _credential_presence["GOOGLE_API_KEY"],
)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
try:
    from core.ollama_client import OllamaClient
    _local_ollama_models = OllamaClient(OLLAMA_URL, timeout=1).list_models()
except Exception:
    _local_ollama_models = []
available_models = available_providers(_credentials, _local_ollama_models)
if not available_models:
    st.error("Model bağlantısı için Streamlit Secrets veya ortam değişkenlerinde GROQ_API_KEY/GOOGLE_API_KEY ya da erişilebilir yerel Ollama modeli gerekli.")
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
                    
        # Instant Answer API is not a full search engine. Return explicit source metadata.
        url = "https://api.duckduckgo.com/?" + urlencode({"q": sorgu, "format": "json", "no_html": 1})
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if response.status_code >= 400:
            return "DuckDuckGo servisi hata döndürdü; güncel bilgi doğrulanamadı."
        data = response.json()
        abstract = data.get("AbstractText")
        source_url = data.get("AbstractURL")
        if isinstance(abstract, str) and abstract.strip():
            if isinstance(source_url, str) and source_url.startswith(("https://", "http://")):
                return "DuckDuckGo anlık yanıt (kaynak: " + source_url + "): " + abstract[:2500]
            return "DuckDuckGo anlık yanıt (kaynak URL'si verilmedi): " + abstract[:2500]
        return "DuckDuckGo anlık yanıtında kaynaklı sonuç bulunamadı; tam web araması yapılamadı."
    except Exception:
        return "İnternet veri kaynağına erişilemedi; güncel bilgi doğrulanamadı."

# 🎛️ SIDEBAR (YAN MENÜ) AYARLARI
st.sidebar.title("🤖 Asistan Kontrol Paneli")
secilen_model = st.sidebar.selectbox(
    "Kullanılacak Yapay Zeka Beyni:",
    available_models
)

if secilen_model.startswith("Ollama (Yerel): "):
    aktif_llm_adi = secilen_model.removeprefix("Ollama (Yerel): ")
    st.sidebar.success(f"Aktif Beyin: Yerel Ollama · {aktif_llm_adi}")
elif "Groq" in secilen_model:
    from groq import Groq
    aktif_llm_adi = "openai/gpt-oss-120b" 
    st.sidebar.success("Aktif Beyin: Groq GPT-OSS ⚡")
else:
    from google import genai
    from google.genai import types
    aktif_llm_adi = os.environ.get("GOOGLE_MODEL", "gemini-3.6-flash")
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

if "Google Gemini" in secilen_model and GOOGLE_KEY and st.sidebar.button("Google bağlantısını doğrula"):
    check = check_provider("google", GOOGLE_KEY, model=aktif_llm_adi)
    if check["status"] == "verified" and check.get("model_available"):
        st.sidebar.success("Google bağlantısı ve seçili model listede doğrulandı; metin üretilmedi.")
    elif check.get("authenticated"):
        st.sidebar.warning("Google kimliği doğrulandı; seçili model erişimi henüz doğrulanamadı. GOOGLE_MODEL ayarını kontrol edin.")
    else:
        st.sidebar.error("Google bağlantısı doğrulanamadı. Ayrıntılar güvenlik için gizlendi.")

# Web Sayfası Başlığı ve Sade Tasarım
st.title("🧠 CANO — Yapay Zekâ Komuta Merkezi")
st.caption("Gerçek görevler · Uzman ekip · Denetim aşamaları · Bilimsel kaynak adayları · Açık kayıt durumu")

# 🎨 Tarayıcı düzeyinde <think> etiketlerini tamamen yok eden CSS kodu
st.markdown(
    """
    <style>
    …4865 tokens truncated…l deposunda saklanır; başka cihazlarla eşitlenmez, kullanıcı tarayıcı verilerini silerse kaybolabilir. Sohbet geçmişi hâlâ oturuma özeldir.\n    - Sol menüde 🧬 Öğrenen uzman ajanlar paneli bulunur: kurucu uzman, izinli alt uzman, onaylı geri bildirimden ders çağırma ve modelle taslak üretme sunar.\n    - En az iki farklı ajan varsa panelde üç aşamalı taslak → eleştiri → düzeltme döngüsü vardır. İnceleme kayıtları oturuma özel SQLite dosyasındadır; sunucu yeniden başlatılınca korunacağı garanti değildir.\n    - Bu geri bildirim kullanımı model ağırlıklarını eğitmez. Uzmanlar otomatik olarak arka planda çoğalan bağımsız süreçler değildir.
    - Kod geliştirme mümkündür ancak bu sohbet arayüzünde doğrudan GitHub, Render, Notion, dosya sistemi veya kod çalıştırma aracı bağlı değildir.
    - Kullanıcı ajan özelliklerini sorarsa önce bu uygulamada gerçekten mevcut olan paneli ve somut kullanım adımlarını anlat; genel bir "kalıcı hafızam yok, kendimi geliştiremem" metniyle mevcut özellikleri inkâr etme.\n    - Kullanıcı senden geliştirme, araştırma, hata giderme veya ajan koordinasyonu istediğinde kategorik olarak "imkansız" deme. Mevcut işlevleri dürüstçe anlat, uygulanabilir teknik çözüm ve kod taslağı sun, eksik bağlantıyı açıkça belirt.
    - Gerçekte çağrılmayan araçları çağırmış, kaydedilmemiş dosyaları kaydetmiş, doğrulanmamış kaynakları doğrulamış gibi gösterme.
    - Yalnızca uygulamaya gerçekten verilen güncel veri varsa bunu güncel olarak sun; veri yoksa güncelliği doğrulayamadığını söyle.

    🧠 KİMLİK BİLGİSİ:
    Bu, Python ve Streamlit ile geliştirilen bir asistan arayüzüdür. Yanıtlar seçilen harici Groq veya Google modeliyle üretilir. Kullanıcı sorarsa sağlayıcıyı doğru tanıt; yapımcı veya model kökeni hakkında doğrulanmamış iddialarda bulunma.
    
    ⚠️ SIKI KURALLAR:
    1. Yanıtının tamamı sadece doğal, akıcı ve kurallı bir Türkçe ile yazılmalıdır.
    2. Kullanıcıya doğrudan bir insan gibi samimi cevap ver, asla yarım bırakma.
    3. Eğer yukarıdaki veri kutusunda 'HAVA SERVİSİ BİLGİSİ' yazmıyorsa, hava durumundan KESİNLİKLE bahsetme. Kullanıcı sana ne sorduysa sadece ona odaklan ve normal bir şekilde sohbet et. Hava durumunu sadece kullanıcı açıkça sorduğunda ver."""

    try:
        raw_response = ""
        if secilen_model.startswith("Ollama (Yerel): "):
            api_mesajlari = [{"role": "system", "content": sistem_talimati}]
            api_mesajlari.extend(
                {"role": msg["role"], "content": msg["content"]}
                for msg in st.session_state.messages
                if msg.get("role") in {"user", "assistant"}
            )
            raw_response = OllamaClient(OLLAMA_URL).chat_messages(
                aktif_llm_adi, api_mesajlari
            )
        elif "Groq" in secilen_model:
            api_mesajlari = [{"role": "system", "content": sistem_talimati}]
            for msg in st.session_state.messages:
                api_mesajlari.append({"role": msg["role"], "content": msg["content"]})
            # Chat UI already adds the current turn before invoking this
            # function. Append only for callers that have not done so.
            if not (api_mesajlari[-1]["role"] == "user" and
                    api_mesajlari[-1]["content"] == kullanici_mesaji):
                api_mesajlari.append({"role": "user", "content": kullanici_mesaji})

            client = Groq(api_key=GROQ_KEY, timeout=25.0, max_retries=0)
            completion = client.chat.completions.create(
                model=aktif_llm_adi,
                messages=api_mesajlari,
                max_tokens=1000 
            )
            # 👑 HATA DÜZELTİLDİ: choices listesinin ilk elemanına [0] ile erişildi!
            raw_response = completion.choices[0].message.content
        else:
            client = genai.Client(api_key=GOOGLE_KEY)
            # Gemini uses the role name "model" for prior assistant turns.
            # Keep the same conversation as the chat UI, including the current
            # user turn exactly once, rather than sending an isolated message.
            google_contents = [
                {"role": "model" if msg["role"] == "assistant" else "user",
                 "parts": [{"text": msg["content"]}]}
                for msg in st.session_state.messages
                if msg.get("role") in {"user", "assistant"}
                and isinstance(msg.get("content"), str)
            ]
            if not (google_contents and google_contents[-1]["role"] == "user"
                    and google_contents[-1]["parts"] == [{"text": kullanici_mesaji}]):
                google_contents.append({"role": "user", "parts": [{"text": kullanici_mesaji}]})
            response = client.models.generate_content(
                model=aktif_llm_adi,
                contents=google_contents,
                config=types.GenerateContentConfig(
                    system_instruction=sistem_talimati,
                    max_output_tokens=1000
                )
            )
            raw_response = response.text

        temiz_cevap = re.sub(r'<(think|thought|düşün).*?(</\1>|$)', '', raw_response, flags=re.DOTALL | re.IGNORECASE)
        return label_research_answer(temiz_cevap, research_requested=arama_istegi)

    except Exception as e:
        logging.getLogger(__name__).warning("Provider request failed: category=%s", failure_category(e))
        return safe_failure_message(e)

# 🔄 SOHBET AKIŞINI EKRANA BASMA (Temiz Hafıza Akışı)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ✍️ KULLANICI GİRİŞ ALANI
st.caption("CANO ekibine gerçekten görev vermek için ‘CANO görev:’ yazıp hedefi ekleyin. "
           "Görev dört kayıtlı model aşamasından geçer; sonuç taslak olarak işaretlenir.")
if prompt := st.chat_input("Asistanınıza dilediğiniz her şeyi sorun..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Explicit memory requests are saved instead of merely promised by an LLM.
    if explicit_memory_request(prompt):
        if len(st.session_state.saved_memories) >= 200:
            result = "Hafıza dolu (en fazla 200 not). Önce eski notlardan birini silin."
        else:
            try:
                _chat_note = new_memory(prompt, ["sohbet"])
                if _MEMORY_STORE is not None:
                    _MEMORY_STORE.save(_OWNER_KEY, _chat_note)
                st.session_state.saved_memories.append(_chat_note)
                if _MEMORY_STORE is None:
                    _stage_browser_memory_write()
                    st.session_state.messages.append({
                        "role": "assistant", "content": "Tarayıcıya yazılıyor; kayıt henüz doğrulanmadı.",
                    })
                    st.session_state["_browser_pending_chat_index"] = len(st.session_state.messages) - 1
                    st.rerun()
                result = "Notu PostgreSQL hafızasına kaydettim."
            except Exception:
                result = "Kayıt başarısız oldu; hafızaya kaydedildiğini söylemiyorum."
        st.session_state.messages.append({"role": "assistant", "content": result})
        with st.chat_message("assistant"):
            st.markdown(result)
        st.stop()

    with st.chat_message("assistant"):
        with st.spinner("Asistanınız yanıt hazırlıyor..."):
            ajan_cevabi = asistani_calistir(prompt)
            st.markdown(ajan_cevabi)
            
            st.session_state.messages.append({"role": "assistant", "content": ajan_cevabi})

# A team task preview never runs a provider call. Each execution needs a fresh,
# task-specific approval form; clearing submission resets the checkbox.
_chat_pending_task = st.session_state.get("_cano_chat_task_pending")
if isinstance(_chat_pending_task, dict):
    with st.chat_message("assistant"):
        with st.form("cano_chat_task_approval", clear_on_submit=True):
            st.info("Görev: " + str(_chat_pending_task.get("task", "")))
            st.caption("Onay verilmeden CANO modeli çağırmaz veya görev kaydı oluşturmaz.")
            _chat_task_approved = st.checkbox(
                "Bu görev için dört model aşamasını başlatmayı onaylıyorum.",
                value=False, key="cano_chat_task_approval_checkbox")
            _chat_task_submit = st.form_submit_button(
                "Dört aşamalı CANO görevini başlat")
            _chat_task_cancel = st.form_submit_button("Bekleyen görevi iptal et")
        if _chat_task_cancel:
            from core.cano_chat_tasks import cancel_pending_task
            if cancel_pending_task(st.session_state):
                st.info("Bekleyen CANO görevi iptal edildi; model çağrısı yapılmadı.")
            else:
                st.warning("Bu onay formu güncel değil; hiçbir görev başlatılmadı.")
            st.rerun()
        elif _chat_task_submit:
            if not _chat_task_approved:
                st.warning("Başlatmak için bu görev özelindeki onay kutusunu işaretleyin.")
            else:
                with st.spinner("Onaylanan CANO görevi yürütülüyor..."):
                    _chat_task_result = asistani_calistir(
                        "CANO görev: " + str(_chat_pending_task.get("task", "")),
                        approved=True)
                st.markdown(_chat_task_result)
                st.session_state.messages.append({
                    "role": "assistant", "content": _chat_task_result,
                })

