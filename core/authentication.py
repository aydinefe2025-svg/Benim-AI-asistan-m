"""Small helpers for fail-closed Streamlit OIDC identity handling."""
from __future__ import annotations

import hashlib
import hmac
from typing import Mapping, Any


def auth_is_required(environment: Mapping[str, str]) -> bool:
    # Only explicit false values disable login. A typo must never turn
    # production authentication off silently (fail closed on invalid values).
    raw = environment.get("APP_AUTH_REQUIRED", "").strip().casefold()
    return raw not in {"", "0", "false", "no", "off"}


def oidc_is_configured(secrets: Any) -> bool:
    try:
        auth = secrets["auth"]
        return all(
            isinstance(auth.get(key), str) and auth.get(key).strip()
            for key in (
                "redirect_uri", "cookie_secret", "owner_key_secret", "client_id",
                "client_secret", "server_metadata_url",
            )
        )
    except Exception:
        return False


def authenticated_owner_key(claims: Any, owner_key_secret: str) -> str | None:
    """Return a stable opaque owner key, separate from the rotatable login cookie."""
    try:
        subject = claims.get("sub")
        issuer = claims.get("iss")
    except Exception:
        return None
    if not all(isinstance(value, str) and value.strip()
               for value in (subject, issuer, owner_key_secret)):
        return None
    message = (issuer.strip() + "\x00" + subject.strip()).encode("utf-8")
    digest = hmac.new(owner_key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return "oidc_" + digest


def render_auth_gate(st: Any, environment: Mapping[str, str]) -> str | None:
    """Stop the Streamlit run unless required Google OIDC is configured and valid."""
    if not auth_is_required(environment):
        return None
    if not oidc_is_configured(st.secrets):
        st.error(
            "Güvenli giriş yapılandırılmamış. Google OIDC ayarlarını Streamlit "
            "Secrets içinde tamamlayın; uygulama kapalı kalacak."
        )
        st.stop()
    user = st.user
    if not user.get("is_logged_in", False):
        st.title("Giriş gerekli")
        st.button("Google ile giriş yap", on_click=st.login)
        st.stop()
    auth = st.secrets["auth"]
    owner_key = authenticated_owner_key(user, auth["owner_key_secret"])
    if owner_key is None:
        st.error("Giriş kimliği doğrulanamadı; oturum başlatılmadı.")
        st.stop()
    st.sidebar.button("Güvenli çıkış", on_click=st.logout, key="logout")
    return owner_key
