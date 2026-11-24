"""Owner-only grant issuance; disabled until an HTTPS gateway is configured."""
from core.local_grant_owner import issue_for_owner, revoke_for_owner

def render_local_grant_owner(st, queue, *, owner_key, environment):
    if not owner_key or queue is None or queue.owner_key != owner_key:
        return
    enabled = environment.get("CANO_LOCAL_GRANT_ENABLED") == "1"
    with st.sidebar.expander("CANO Windows HTTPS görev aktarımı", expanded=False):
        try:
            queue.verify_schema()
            active = [j for j in queue.list() if j.get("state") == "running"
                      and (j.get("worker_id") or "").startswith(("local-http-ready:","local-http-taken:"))]
        except Exception:
            st.warning("Görev kuyruğu doğrulanamadı; yeni yetki verilmedi.")
            return
        if not enabled:
            st.caption("HTTPS ağ aktarımı etkin değil. Dosya aktarımı kullanılabilir.")
        else:
            st.caption("Sıradaki onaylı görev için tek kullanımlık yetki. En fazla 60 dakika. "
                       "Yetkiyi yalnız kendi Windows terminalinize yapıştırın.")
            with st.form("cano_network_grant_issue", clear_on_submit=True):
                approved = st.checkbox("Tek bir görevin yerel modele aktarılmasını onaylıyorum.")
                submit = st.form_submit_button("Tek görev yetkisi oluştur")
            if submit:
                if not approved:
                    st.warning("Açık onay gerekli.")
                else:
                    try:
                        receipt = issue_for_owner(queue,owner_key=owner_key,environment=environment,approved=True)
                        if receipt is None:
                            st.info("Uygun görev yok.")
                        else:
                            st.code(receipt["grant"])
                            st.caption("Yetki yalnız bu görüntülemede gösterilir; paylaşmayın.")
                    except Exception:
                        st.error("Yetki kaydı belirsiz; görev durumunu kontrol edin. Otomatik tekrar yok.")
        if active:
            jobs = {j["id"]: j for j in active}
            with st.form("cano_network_grant_revoke", clear_on_submit=True):
                chosen = st.selectbox("İptal edilecek görev",list(jobs),format_func=lambda j:j[:8])
                approval = st.checkbox("Bu görevin yerel yetkisini iptal edip işi engellemeyi onaylıyorum.")
                submit = st.form_submit_button("Yetkiyi iptal et")
            if submit:
                if not approval:
                    st.warning("İptal için açık onay gerekli.")
                else:
                    try:
                        revoke_for_owner(queue,chosen,owner_key=owner_key,approved=True)
                        st.success("Yetki iptal edildi; görev yeniden çalıştırılmadı.")
                    except Exception:
                        st.warning("Yetki iptali doğrulanamadı; kuyruk durumunu inceleyin.")
