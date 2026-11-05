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
from core.storage_config import cano_database_url, memory_database_url

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
    if _MEMORY_STORE is not None:
        try:
            st.session_state.saved_memories = _MEMORY_STORE.list(_OWNER_KEY)
        except Exception:
            st.error(
                "Kalıcı hafıza şeması veya veritabanı izinleri hazır değil; "
                "kayıtlar değiştirilmedi."
            )
            st.stop()
    else:
        st.session_state.saved_memories = []

# Browser-local fallback: verify the storage bridge before permitting writes.
# PostgreSQL remains the account-scoped backend when configured.
def _stage_browser_memory_write():
    st.session_state["_browser_pending"] = {
        "token": str(uuid4()),
        "payload": export_library(st.session_state.saved_memories),
    }


if _MEMORY_STORE is None:
    _browser_snapshot = browser_memory_component(st.session_state.get("_browser_pending"))
    if _browser_snapshot is None:
        st.info("Tarayıcı hafızası yükleniyor; kayıtlara henüz dokunulmadı.")
        st.stop()
    try:
        _browser_reloaded = decode_snapshot(_browser_snapshot)
    except ValueError:
        st.error("Tarayıcı hafızası okunamadı. Verilerin üzerine yazılmadı; varsa JSON yedeğinizi saklayın.")
        st.stop()
    if not st.session_state.get("_browser_loaded"):
        st.session_state.saved_memories = _browser_reloaded
        st.session_state["_browser_loaded"] = True
    _pending_write = st.session_state.get("_browser_pending")
    if _pending_write is not None:
        if write_confirmed(_browser_snapshot, _pending_write):
            st.session_state.pop("_browser_pending", None)
            _pending_chat_idx = st.session_state.pop("_browser_pending_chat_index", None)
            if isinstance(_pending_chat_idx, int) and 0 <= _pending_chat_idx < len(st.session_state.messages):
                st.session_state.messages[_pending_chat_idx]["content"] = (
                    "Notu bu tarayıcının hafızasına kaydettim ve geri okuyarak doğruladım. "
                    "Farklı cihazda görünmez; tarayıcı verilerini silerseniz kaybolabilir."
                )
            st.toast("Tarayıcı hafızası: kaydetme ve geri okuma başarılı.")
        elif _browser_snapshot.get("ack") != _pending_write["token"]:
            st.info("Tarayıcı hafızasına kaydediliyor...")
            st.stop()
        else:
            st.error("Tarayıcı hafızasına yazma doğrulanamadı; JSON yedeği alın.")
            st.stop()


with st.sidebar.expander("🧠 Hafıza kitaplığım", expanded=False):
    st.caption(
        "Yalnızca açıkça eklediğiniz notlar sonraki yanıtlara bağlam olur. "
        "Bu, modelin eğitildiği anlamına gelmez. "
        + ("Notlar giriş hesabınıza bağlı PostgreSQL'de saklanır. "
           if _MEMORY_STORE is not None else
           "Notlar bu tarayıcıda tutulur; farklı cihazlara eşitlenmez. Tarayıcı verilerini silerseniz kaybolabilir, JSON yedek indirin. ")
        +
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
                imported = import_library(memory_upload.getvalue())
                if _MEMORY_STORE is not None:
                    combined = {item["id"]: item for item in st.session_state.saved_memories}
                    combined.update({item["id"]: item for item in imported})
                    _MEMORY_STORE.save_many(_OWNER_KEY, list(combined.values()))
                    st.session_state.saved_memories = _MEMORY_STORE.list(_OWNER_KEY)
                else:
                    st.session_state.saved_memories = imported
                    _stage_browser_memory_write()
                    st.rerun()
                st.success(f"{len(st.session_state.saved_memories)} not içe aktarıldı.")
            except (ValueError, UnicodeError):
                st.error("Kitaplık dosyası geçersiz veya desteklenmiyor; içerik okunmadı.")
            except Exception:
                st.error("Kitaplık kaydedilemedi; veritabanı kayıtları değiştirilmedi.")

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
                try:
                    if _MEMORY_STORE is not None:
                        _MEMORY_STORE.save(_OWNER_KEY, item)
                    st.session_state.saved_memories.append(item)
                    if _MEMORY_STORE is None:
                        _stage_browser_memory_write()
                        st.rerun()
                    st.success("Not hafıza kitaplığına eklendi.")
                except Exception:
                    st.error("Not kaydedilemedi; mevcut kayıtlar korundu.")
        except ValueError:
            st.warning("Kaydetmek için 1–2000 karakter arasında bir not yazın.")

    if st.session_state.saved_memories:
        st.caption(f"Bu oturumda {len(st.session_state.saved_memories)} kayıtlı not var.")
        for index, item in enumerate(st.session_state.saved_memories):
            st.markdown(f"**{index + 1}.** {item['text']}")
            if st.button("Sil", key=f"delete_memory_{item['id']}"):
                try:
                    if _MEMORY_STORE is not None:
                        _MEMORY_STORE.delete(_OWNER_KEY, item["id"])
                    st.session_state.saved_memories = [
                        saved for saved in st.session_state.saved_memories
                        if saved["id"] != item["id"]
                    ]
                    if _MEMORY_STORE is None:
                        _stage_browser_memory_write()
                    st.rerun()
                except Exception:
                    st.error("Not silinemedi; kayıt olduğu gibi korundu.")

# User-controlled research task ledger; no automatic execution.
def _research_leads(goal: str) -> str:
    scholarly = []
    try:
        scholarly = scientific_sources(goal)
    except Exception:
        pass
    try:
        leads = research_sources(goal)
    except Exception:
        leads = []
    leads = scholarly + leads
    if not leads:
        return "No sources retrieved; independent verification pending."
    return "Metadata/source leads only; primary-source review required: " + "; ".join(
        item["title"] + ": " + item["url"] for item in leads)


def _research_answer(goal: str) -> str:
    if not GROQ_KEY:
        raise RuntimeError("Groq key unavailable")
    from groq import Groq
    client = Groq(api_key=GROQ_KEY, timeout=25.0, max_retries=0)
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": "You are a research drafting assistant. Clearly distinguish uncertain claims. Do not invent citations, claim web browsing, or claim independent verification. Answer in Turkish."},
            {"role": "user", "content": goal[:30000] + " | Sources: " + _research_leads(goal[:1200])},
        ],
        max_tokens=2400,
        temperature=0.2,
    )
    output = response.choices[0].message.content or ""
    if response.choices[0].finish_reason == "length":
        output += "\n\n[UYARI: Model yanıtı token sınırında kesildi; içerik eksik olabilir.]"
    return output


def _team_answer(prompt: str) -> str:
    # Short, user-triggered specialist calls never start implicit web searches.
    # Provider quota errors leave resumable stage checkpoints.
    return generate_team_stage(prompt, api_key=GROQ_KEY)


_CANO_OWNER_KEY = _OWNER_KEY if _AUTH_REQUIRED and _OWNER_KEY else None
render_cano_command_center(
    st, answer=_team_answer if GROQ_KEY else None,
    owner_key=_CANO_OWNER_KEY,
    database_url=cano_database_url(os.environ) if _CANO_OWNER_KEY else None,
)
render_task_panel(st, answer=_research_answer if GROQ_KEY else None, store_override=_TASK_STORE)
render_authorized_queue_panel(
    st, answer=_research_answer if GROQ_KEY else None,
    owner_key=_OWNER_KEY if _TASK_STORE is not None else None,
    database_url=os.environ.get("AGENT_TASK_DATABASE_URL") if _TASK_STORE is not None else None,
)
render_colony_panel(st, answer=_team_answer if GROQ_KEY else None,
                    owner_key=_CANO_OWNER_KEY,
                    database_url=cano_database_url(os.environ) if _CANO_OWNER_KEY else None)

# 🧠 Modeli Doğrudan Tetikleyen Arka Plan Sistemi
def asistani_calistir(kullanici_mesaji, *, approved=False):
    from core.cano_chat_tasks import parse_task_request, format_task_result
    task_goal = parse_task_request(kullanici_mesaji)
    if task_goal is not None:
        request_key = "cano_chat_request_id"
        pending = st.session_state.get(request_key)
        if approved:
            # Approval can execute only the exact task/id previously previewed.
            # Do not allocate a new request during approval: duplicate form
            # submits and stale approvals must remain read-only.
            preview = st.session_state.get("_cano_chat_task_pending")
            if (not isinstance(pending, dict)
                    or not isinstance(preview, dict)
                    or pending.get("task") != task_goal
                    or preview.get("task") != task_goal
                    or not isinstance(pending.get("id"), str)
                    or preview.get("id") != pending.get("id")):
                return ("Bu CANO görevi için geçerli bekleyen onay bulunamadı. "
                        "Görevi yeniden yazıp yeni bir onay oluşturun; model "
                        "çağrısı veya görev kaydı başlatılmadı.")
        elif not isinstance(pending, dict) or pending.get("task") != task_goal:
            pending = {"task": task_goal, "id": str(uuid4())}
            st.session_state[request_key] = pending
        if not approved:
            st.session_state["_cano_chat_task_pending"] = pending
            return ("CANO görev taslağı hazır: " + task_goal + "\n"
                    "Henüz model çağrısı veya görev kaydı yapılmadı. Aşağıdaki onay "
                    "kutusunu bu görev için işaretleyip başlat düğmesine basarsanız "
                    "dört model aşaması çalışır; sonuç inceleme bekleyen taslak olur.")
        if not GROQ_KEY:
            return ("CANO görevini sohbetten dört aşamalı ekibe yönlendiremedim: "
                    "ekip yürütücüsü için Groq anahtarı yapılandırılmamış. "
                    "Bu istek sıradan sohbet yanıtı gibi gösterilmedi.")
        try:
            from core.agent_colony import AgentColony
            from core.collaborative_mission import CollaborativeMission
            from core.cano_command_center import (
                _AnswerAdapter, _snapshot, prepare_cano_team,
            )
            from core.colony_postgres import ColonySnapshotStore
            from core.colony_restore import restore_empty_colony
            from core.task_panel import _session_database_path

            owner = globals().get("_CANO_OWNER_KEY")
            db_path = _session_database_path(
                st, os.environ.get("AGENT_COLONY_DB_PATH", "data/agent_colony.sqlite3"))
            colony = AgentColony(db_path, max_agents=12)
            mission_manager = CollaborativeMission(colony)
            store = None
            if owner:
                database_url = cano_database_url(os.environ)
                if not database_url:
                    raise RuntimeError("Hesaba bağlı CANO PostgreSQL adresi bulunamadı")
                store = ColonySnapshotStore(database_url)
                store.verify_schema()
                if st.session_state.get("_cano_backup_owner_key") != owner:
                    if st.session_state.get("_cano_backup_owner_key") is not None:
                        raise RuntimeError("Giriş hesabı değişti; yeni oturum açın")
                    st.session_state["_cano_backup_owner_key"] = owner
                remote = store.load(owner)
                with colony._db() as db:
                    local_agents = db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]
                if not local_agents and remote is not None and any(
                        remote.get(name) for name in ("agents", "feedback", "reviews", "missions")):
                    restore_empty_colony(colony, remote)
                    st.session_state["_cano_backup_expected"] = store.load(owner)
                elif "_cano_backup_expected" not in st.session_state:
                    if local_agents and remote != _snapshot(colony):
                        raise RuntimeError("Yerel ekip ile hesaba bağlı kayıt eşleşmiyor")
                    st.session_state["_cano_backup_expected"] = remote

            def checkpoint(*, archive_prior=False):
                if store is not None:
                    snapshot = _snapshot(colony)
                    store.save_versioned_verified(
                        owner, snapshot,
                        expected_prior=st.session_state["_cano_backup_expected"],
                        archive_prior=archive_prior)
                    st.session_state["_cano_backup_expected"] = snapshot

            # Check storage access before initializing or calling a model.
            checkpoint()
            with colony._db() as db:
                agent_count = db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]
            if not agent_count:
                prepare_cano_team(colony, approved=True)
                checkpoint()

            result = mission_manager.execute(
                task_goal, client=_AnswerAdapter(_team_answer),
                model="configured-groq-team", mission_id=pending["id"],
                on_checkpoint=lambda: checkpoint(archive_prior=False) if store else None)
            checkpoint(archive_prior=False)
            st.session_state["cano_cockpit_latest_mission"] = result["id"]
            st.session_state.pop(request_key, None)
            st.session_state.pop("_cano_chat_task_pending", None)
            return format_task_result(result)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "CANO chat task failed: category=%s", failure_category(exc))
            return ("CANO görevi tamamlanmadı. Başarısız model aşaması tekrar "
                    "başlatılmadı ve uydurma sonuç gösterilmiyor. Komuta Merkezi'ndeki "
                    "görev geçmişinden engellenen kaydı inceleyip sürdürün; PostgreSQL "
                    "kayıt hatasında tekrar denemeden önce yedek durumunu kontrol edin.")
    from core.cano_capabilities import capability_reply
    capability = capability_reply(
        kullanici_mesaji,
        persistent_memory=globals().get("_MEMORY_STORE") is not None,
        persistent_colony=bool(globals().get("_CANO_OWNER_KEY")
                               and cano_database_url(os.environ)),
    )
    if capability is not None:
        return capability
    # Avoid unrequested external lookups and leaking casual chat to third parties.
    arama_istegi = any(k in kullanici_mesaji.casefold() for k in (
        "araştır", "internette", "internetten", "webde", "web'de",
        "güncel", "kaynak", "haber", "hava", "sıcaklık", "yağış",
    ))
    arama_sonucu = internette_ara(kullanici_mesaji) if arama_istegi else (
        "Bu mesaj için harici kaynak sorgulanmadı; güncel veri doğrulanmadı."
    )
    
    # Public source lookup only on explicit research requests; source URLs are
    # evidence pointers, not proof that model claims were independently verified.
    if arama_istegi:
        try:
            public_sources = research_sources(kullanici_mesaji)
            if public_sources:
                arama_sonucu += "\nAçık ansiklopedi kaynakları (bağımsız doğrulanmadı):\n" + "\n".join(
                    item["title"] + ": " + item["url"] for item in public_sources
                )
        except (OSError, ValueError, KeyError, TypeError):
            arama_sonucu += "\nAçık kaynak araması başarısız; sonuç doğrulanamadı."
    saved_context = memory_context(st.session_state.saved_memories, kullanici_mesaji)
    storage_context = (
        "Hafıza notları şu anda doğrulanmış giriş hesabının PostgreSQL deposunda saklanır."
        if globals().get("_MEMORY_STORE") is not None else
        "Bu oturumdaki hafıza notları yalnızca tarayıcı deposundadır."
    )
    sistem_talimati = f"""Sen sadece Türkçe konuşan, samimi ve harika bir dijital asistansın.
    İnternetten senin için gelen veri kutusu şudur: {arama_sonucu}
    {saved_context}
    GÜNCEL ÇALIŞMA DURUMU: {storage_context}
    
    🧰 GERÇEK YETENEKLER VE SINIRLAR:
    - Bu uygulama, yapılandırılmış Groq veya Google modeliyle yanıt üretir.
    - internette_ara() DuckDuckGo anlık yanıtını ve şehir belirtilirse wttr.in hava servisini sorgular. Ayrıca açık ansiklopedi arama bağlantıları toplanabilir; bunlar bağımsız doğrulama değildir. Tam web tarayıcısı değildir.
    - Araştırma/görev paneli kullanıcı denetimli taslak ve kayıt işlevi sunar; görevleri arka planda kendiliğinden yürütmez.
    - Hafıza notları DATABASE_URL ve doğrulanmış giriş yapılandırılmışsa PostgreSQL üzerinde kalıcıdır. Aksi halde yalnızca bu tarayıcının yerel deposunda saklanır; başka cihazlarla eşitlenmez, kullanıcı tarayıcı verilerini silerse kaybolabilir. Sohbet geçmişi hâlâ oturuma özeldir.\n    - Sol menüde 🧬 Öğrenen uzman ajanlar paneli bulunur: kurucu uzman, izinli alt uzman, onaylı geri bildirimden ders çağırma ve modelle taslak üretme sunar.\n    - En az iki farklı ajan varsa panelde üç aşamalı taslak → eleştiri → düzeltme döngüsü vardır. İnceleme kayıtları oturuma özel SQLite dosyasındadır; sunucu yeniden başlatılınca korunacağı garanti değildir.\n    - Bu geri bildirim kullanımı model ağırlıklarını eğitmez. Uzmanlar otomatik olarak arka planda çoğalan bağımsız süreçler değildir.
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
        if _chat_task_submit:
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
