"""Small helpers for fail-closed Streamlit OIDC identity handling."""
from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlsplit
from typing import Mapping, Any


def auth_is_required(environment: Mapping[str, str]) -> bool:
    # Only explicit false values disable login. A typo must never turn
    # production authentication off silently (fail closed on invalid values).
    raw = environment.get("APP_AUTH_REQUIRED", "").strip().casefold()
    return raw not in {"", "0", "false", "no", "off"}


def oidc_is_configured(
    secrets: Any, environment: Mapping[str, str] | None = None,
) -> bool:
    """Check the OIDC callback shape and its Render public origin, never secrets."""
    try:
        auth = secrets["auth"]
        if not all(
            isinstance(auth.get(key), str) and auth.get(key).strip()
            for key in (
                "redirect_uri", "cookie_secret", "owner_key_secret", "client_id",
                "client_secret", "server_metadata_url",
            )
        ):
            return False

        callback = urlsplit(auth["redirect_uri"].strip())
        if (callback.path != "/oauth2callback" or callback.query
                or callback.fragment or callback.hostname is None
                or callback.username or callback.password):
            return False

        env = environment or {}
        public_url = env.get("RENDER_EXTERNAL_URL", "").strip()
        on_render = env.get("RENDER", "").strip().casefold() == "true"
        if callback.scheme != "https":
            if not (callback.scheme == "http"
                    and callback.hostname in {"localhost", "127.0.0.1"}
                    and not public_url and not on_render):
                return False
        if public_url:
            public = urlsplit(public_url)
            if callback.scheme != public.scheme or callback.netloc != public.netloc:
                return False
        elif on_render:
            # A Render app has a known public URL; do not guess a login origin.
            return False
        return True
    except Exception:
        # No credentials or raw parser exception should reach a browser or log.
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



def isolate_owner_session(state: Any, owner_key: str | None) -> bool:
    """Prevent a previous OIDC owner's Streamlit in-memory data from leaking.

    Streamlit can rerun inside the same browser session with a different
    authenticated user. An owner-key change must invalidate ALL old session
    data, not just visible chat: memory notes, tasks, export buffers, model
    results and unknown future data-bearing widget keys. Retain only harmless
    non-owner appearance and the already-created logout widget key.
    """
    marker = "_cano_session_owner"
    if marker in state and state.get(marker) == owner_key:
        return False
    # A legacy session without a marker is NOT a trusted same-owner session.
    # Fail closed so a hot deployment cannot expose stale owner-owned data.
    harmless_ui_keys = frozenset(("user_theme", "logout"))
    for key in list(state):
        if key not in harmless_ui_keys:
            state.pop(key, None)
    state[marker] = owner_key
    return True


def render_auth_gate(st: Any, environment: Mapping[str, str]) -> str | None:
    """Stop the Streamlit run unless required Google OIDC is configured and valid."""
    if not auth_is_required(environment):
        return None
    if not oidc_is_configured(st.secrets, environment):
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
