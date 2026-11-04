"""Explicit, authenticated Streamlit control for the persistent CANO task queue.

No automatic model calls or silently started workers. The authenticated OIDC
owner key must be supplied by app.py; a PostgreSQL connection alone is not
authority to run another person's task. Provider drafts are not verification.
"""
from __future__ import annotations

import logging
import uuid

from core.postgres_authorized_queue import PostgresAuthorizedQueue


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
