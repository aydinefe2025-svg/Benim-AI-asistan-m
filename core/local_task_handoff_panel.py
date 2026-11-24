"""Authenticated owner-operated local file transfer controls."""
from core.local_task_handoff import claim_ticket, accept_result, encode_file, parse_file

_KEY = "_cano_local_handoff_private"


def render_local_task_handoff(st, queue, *, owner_key):
    if not owner_key or queue is None or queue.owner_key != owner_key:
        return
    with st.sidebar.expander("💻 CANO Windows yerel görev aktarımı", expanded=False):
        st.caption("Tek onaylı kuyruk işi, tek yerel model çağrısı. Görev ve sonuç "
                   "dosyaları şifreli değildir; yalnız kendi cihazınızda saklayın. "
                   "Aynı giriş oturumunu açık tutun (en fazla 60 dakika). "
                   "Bu özellik otomatik ağ işçisi veya doğrulanmış araştırma değildir.")
        active = st.session_state.get(_KEY)
        if active is not None and active.get("owner_key") != owner_key:
            st.session_state.pop(_KEY, None)
            active = None
        if active is None:
            with st.form("cano_local_handoff_claim", clear_on_submit=True):
                approved = st.checkbox("Sıradaki uygun işi Windows'a aktarmayı ve bir yerel model denemesini onaylıyorum.")
                submitted = st.form_submit_button("Yerel görev dosyasını hazırla")
            if submitted:
                if not approved:
                    st.warning("Açık onay gerekli.")
                else:
                    try:
                        active = claim_ticket(queue, approved=True)
                        if active is None:
                            st.info("Uygun kuyruk işi yok.")
                        else:
                            st.session_state[_KEY] = active
                    except Exception:
                        st.error("Aktarım kaydı belirsiz; kuyruk durumunu inceleyin, tekrar başlatmayın.")
        if active is None:
            return
        ticket = active["ticket"]
        st.caption("Yerel aktarım: " + ticket["job_id"][:8])
        st.download_button("Windows görev dosyasını indir", data=encode_file(ticket),
                           file_name="cano-local-task-" + ticket["job_id"][:8] + ".json",
                           mime="application/json", key="cano_local_handoff_download")
        st.code("python -m core.local_task_worker <görev-dosyası> --approved",
                language="powershell")
        with st.form("cano_local_handoff_import", clear_on_submit=True):
            upload = st.file_uploader("Windows sonuç dosyası", type=["json"])
            approved = st.checkbox("Bu yerel taslağı hesabımdaki aynı işe kaydetmeyi onaylıyorum.")
            submitted = st.form_submit_button("Yerel sonucu doğrula ve kaydet")
        if submitted:
            if upload is None or not approved:
                st.warning("Sonuç dosyası ve açık onay gerekli.")
            else:
                try:
                    receipt = accept_result(queue, active, parse_file(upload.getvalue()), approved=True)
                    if receipt["readback"]:
                        st.session_state.pop(_KEY, None)
                        st.success("Yerel taslak kaydedildi ve geri okundu; bağımsız doğrulama bekliyor.")
                except Exception:
                    st.error("Sonuç kabul edilmedi veya kayıt belirsiz. Mevcut görev korunuyor; otomatik tekrar yok.")
        if st.button("Aktarım oturumunu bırak (iş yeniden başlatılmaz)", key="cano_local_handoff_abandon"):
            st.session_state.pop(_KEY, None)
            st.warning("Yerel aktarım kaydı bırakıldı. Kuyruk işi süre dolunca manuel inceleme gerektirir.")
