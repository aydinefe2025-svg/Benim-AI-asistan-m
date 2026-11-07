"""Small Streamlit control for creating password-protected local downloads."""
from __future__ import annotations

from hashlib import sha256

from core.backup_encryption import prepare_encrypted_download


def render_encrypted_download(st, *, label: str, filename: str,
                              plaintext: bytes, storage_key: str) -> None:
    if not isinstance(plaintext, bytes) or not plaintext:
        st.warning("Yedek paketi oluşturulamadı; hiçbir dosya indirilmedi.")
        return
    if len(plaintext) > 20 * 1024 * 1024:
        st.error("Yedek paketi 20 MiB sınırını aşıyor.")
        return
    digest = sha256(plaintext).hexdigest()
    encrypted_key = storage_key + "_encrypted"
    if st.session_state.get(storage_key + "_source_digest") != digest:
        st.session_state[encrypted_key] = None
        st.session_state[storage_key + "_source_digest"] = digest

    with st.expander("🔐 Taşınabilir şifreli yedek", expanded=False):
        st.caption(
            "Yedek bu düğmeyle hazırlanıp bu cihaza indirilir. "
            "Parola şifreleme için CANO sunucusuna iletilir ve işlemden sonra "
            "form alanlarından temizlenir. Şifreli dosya geçici oturumda tutulur; "
            "bağımsız otomatik yedek oluşturulmaz. En az 12 karakter kullanın; "
            "parola kaybolursa dosya açılamaz. İndirdiğiniz .canoenc dosyasını "
            "CANO/Neon dışında güvenli bir yerde saklayın."
        )
        with st.form(storage_key + "_form"):
            st.text_input("Yedek parolası", type="password",
                          key=storage_key + "_passphrase", max_chars=1024)
            st.text_input("Parolayı tekrar yazın", type="password",
                          key=storage_key + "_confirm", max_chars=1024)
            st.form_submit_button(
                "Şifreli paketi hazırla",
                on_click=prepare_encrypted_download,
                args=(st, storage_key, plaintext),
            )
        error = st.session_state.get(storage_key + "_error")
        if error:
            st.error(error)
        encrypted = st.session_state.get(encrypted_key)
        if isinstance(encrypted, bytes):
            st.download_button(
                label, data=encrypted, file_name=filename,
                mime="application/octet-stream", key=storage_key + "_download",
            )

