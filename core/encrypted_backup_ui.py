"""Small Streamlit control for creating password-protected local downloads."""
from __future__ import annotations

from hashlib import sha256
import json

from core.backup_encryption import prepare_encrypted_download
from core.cano_backup_bundle import verify_portable_bundle



def _stable_source_digest(plaintext: bytes) -> str:
    """Invalidate prepared downloads only when verified backup content changes.

    The portable archive's creation timestamp and ZIP entry timestamps change
    on every Streamlit rerun even when owner records are unchanged. Hash its
    verified manifest without the non-data creation timestamp instead.
    Non-portable payloads retain the original byte-exact identity behavior.
    """
    try:
        files = verify_portable_bundle(plaintext)
    except ValueError:
        return sha256(plaintext).hexdigest()
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    manifest.pop("created_at", None)
    stable = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(stable).hexdigest()



def _discard_prepared_download(st, storage_key: str) -> None:
    """Fail closed if the current backup source cannot be safely exported."""
    for suffix in ("_encrypted", "_source_digest", "_error"):
        st.session_state.pop(storage_key + suffix, None)
    st.session_state[storage_key + "_passphrase"] = ""
    st.session_state[storage_key + "_confirm"] = ""


def render_encrypted_download(st, *, label: str, filename: str,
                              plaintext: bytes, storage_key: str) -> None:
    if not isinstance(plaintext, bytes) or not plaintext:
        _discard_prepared_download(st, storage_key)
        st.warning("Yedek paketi oluşturulamadı; hiçbir dosya indirilmedi.")
        return
    if len(plaintext) > 20 * 1024 * 1024:
        _discard_prepared_download(st, storage_key)
        st.error("Yedek paketi 20 MiB sınırını aşıyor.")
        return
    digest = _stable_source_digest(plaintext)
    encrypted_key = storage_key + "_encrypted"
    if st.session_state.get(storage_key + "_source_digest") != digest:
        st.session_state[encrypted_key] = None
        st.session_state[storage_key + "_source_digest"] = digest

    with st.expander("🔐 Taşınabilir şifreli yedek", expanded=False):
        st.caption(
            "Yedek bu düğmeyle yalnızca bu cihaza indirilir. Parola CANO'ya gönderilmez "
            "ve saklanmaz. En az 12 karakter kullanın; parola kaybolursa dosya açılamaz. "
            "İndirdiğiniz .canoenc dosyasını CANO/Neon dışında güvenli bir yerde saklayın."
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

