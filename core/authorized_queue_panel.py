"""Explicit, authenticated Streamlit control for the persistent CANO task queue.

No automatic model calls or silently started workers. The authenticated OIDC
owner key must be supplied by app.py; a PostgreSQL connection alone is not
authority to run another person's task. Provider drafts are not verification.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from core.postgres_authorized_queue import PostgresAuthorizedQueue


_STATE_LABELS = {
    "queued": "Kuyrukta",
    "running": "Çalışıyor",
    "review_pending": "İnceleme bekliyor",
    "blocked": "Engellendi",
}
_EVENT_LABELS = {
    ("queued", "explicit_approval"): "İş kullanıcı onayıyla kuyruğa eklendi.",
    ("running", "authorized_claim"): "Bir sağlayıcı denemesi kullanıcı onayıyla başlatıldı.",
    ("review_pending", "unverified_draft_saved"): "Doğrulanmamış taslak kaydedildi.",
    ("queued", "retry_requires_explicit_run"): "Deneme başarısız; tekrar için bekleme süresi ve yeni kullanıcı onayı gerekiyor.",
    ("blocked", "call_budget_exhausted"): "Deneme bütçesi tükendi; iş engellendi.",
    ("blocked", "lease_expired_manual_review"): "Çalışan süresi doldu; olası tekrar öncesi manuel inceleme gerekiyor.",
}


def format_queue_event(event):
    """Render a bounded allowlisted queue event without exposing raw DB fields."""
    if not isinstance(event, dict):
        raise ValueError("Queue event must be an object")
    state = event.get("state")
    label = _STATE_LABELS.get(state, "Durum bilinmiyor")
    description = _EVENT_LABELS.get((state, event.get("code")), "Kuyruk olayı kaydedildi.")
    value = event.get("at")
    try:
        if isinstance(value, datetime):
            moment = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        else:
            moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
        timestamp = moment.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OverflowError, OSError, TypeError, ValueError):
        timestamp = "Zaman bilinmiyor"
    return f"{timestamp} · {label}: {description}"


def render_authorized_queue_panel(st, answer=None, *, owner_key=None, database_url=None):
    if not owner_key or not database_url:
        # Never initialize a shared queue for anonymous users or ephemeral state.
        return
    with st.sidebar.expander("🧰 CANO onaylı görev kuyruğu", expanded=False):
        st.caption(
            "Giriş yaptığınız hesaba ait PostgreSQL iş kuyruğudur. Görev kaydı ve "
            "her model çağrısı için ayrı açık onay gerekir; arka planda ajan çalışmaz. "
            "Çıktılar doğrulanmamış taslaktır."
        )
        try:
            queue = PostgresAuthorizedQueue(database_url, owner_key=owner_key, max_jobs=100)
            queue.verify_schema()
        except Exception as exc:
            # Record only the exception type; database errors may include URLs or credentials.
            logging.getLogger(__name__).warning(
                "Authorized queue initialization failed (%s)", type(exc).__name__
            )
            st.error("Güvenli PostgreSQL görev kuyruğu açılamadı; hiçbir iş çalıştırılmadı.")
            return

        with st.form("cano_persistent_queue_form", clear_on_submit=True):
            goal = st.text_area("Araştırma hedefi", key="cano_queue_goal", max_chars=1200)
            idempotency = st.text_input(
                "Tekil iş anahtarı (yeniden gönderimde aynı kalmalı)",
                key="cano_queue_idempotency", max_chars=120
            )
            max_calls = st.selectbox(
                "Toplam sağlayıcı denemesi üst sınırı", [1, 2, 3],
                key="cano_queue_max_calls"
            )
            approved_enqueue = st.checkbox(
                "Bu görevin hesabımın kuyruğuna kaydedilmesine izin veriyorum",
                key="cano_queue_approve_enqueue"
            )
            submitted = st.form_submit_button("Onaylı görevi kuyruğa ekle")

        if submitted:
            if not approved_enqueue:
                st.warning("Görevi kaydetmek için açık onay gerekli.")
            else:
                try:
                    job = queue.enqueue(idempotency, goal, approved=True, max_calls=max_calls)
                    st.success("Görev kaydı doğrulandı: " + job["id"][:8])
                    st.rerun()
                except (PermissionError, ValueError, RuntimeError):
                    st.warning("Görev reddedildi; tekil anahtar, kota veya alanları kontrol edin.")
                except Exception:
                    st.error("Görev kaydedilemedi; önceki kayıtlar değiştirilmedi.")

        try:
            jobs = queue.list()
        except Exception:
            st.error("Görevler okunamadı; işlem yapılmadı.")
            return
        st.caption("Hesaba ait kuyruk kayıtları: " + str(len(jobs)))
        for job in jobs[-10:]:
            st.caption(job["id"][:8] + " — " + job["state"]
                       + " — deneme " + str(job["attempts"])
                       + "/" + str(job["max_calls"]))
            if job["state"] == "review_pending" and job.get("draft"):
                st.text_area(
                    "Doğrulanmamış taslak " + job["id"][:8],
                    value=job["draft"], disabled=True, height=120,
                    key="cano_queue_draft_" + job["id"],
                )

            with st.expander("Denetim geçmişi " + job["id"][:8], expanded=False):
                try:
                    audit_events = queue.events(job["id"])
                    if audit_events:
                        for event in audit_events[-12:]:
                            st.write(format_queue_event(event))
                    else:
                        st.caption("Henüz kuyruk olayı yok.")
                except Exception:
                    st.warning("Bu işin denetim geçmişi okunamadı; hiçbir kayıt değiştirilmedi.")

        if answer is None:
            st.info("Model sağlayıcısı bağlı değil; işler kaydedilebilir ancak yürütülemez.")
            return
        with st.form("cano_queue_run_form", clear_on_submit=True):
            approved_run = st.checkbox(
                "Sıradaki uygun görev için yalnızca bir model çağrısına izin veriyorum",
                key="cano_queue_approve_run"
            )
            execute = st.form_submit_button("Sıradaki onaylı görevi bir kez çalıştır")
        if execute:
            if not approved_run:
                st.warning("Model çağrısı için ayrıca açık onay gerekli.")
                return
            try:
                queue.recover_expired()
                result = queue.run_once("ui-" + uuid.uuid4().hex,
                                        answer, approved=True)
                if result is None:
                    st.info("Şu anda yürütülebilir onaylı görev bulunmuyor.")
                elif result["status"] == "review_pending":
                    st.success("Görev taslağı kaydedildi; bağımsız kaynak doğrulaması gerekiyor.")
                    st.rerun()
                else:
                    st.warning("Görev güvenli biçimde engellendi veya sınırlı yeniden deneme bekliyor.")
            except (ValueError, PermissionError, RuntimeError):
                st.warning("İşçi veya görev yetkisi doğrulanamadı; model çağrısı tamamlanmadı.")
            except Exception:
                st.error("Kuyruk çalışması başarısız; hata ayrıntıları veya anahtarlar gösterilmedi.")
