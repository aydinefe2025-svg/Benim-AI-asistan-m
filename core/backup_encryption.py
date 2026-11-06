"""Password-based authenticated encryption for portable CANO backup files."""
from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


MAGIC = b"CANOENC1"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSPHRASE_CHARS = 12
MAX_PASSPHRASE_CHARS = 1024
MAX_PLAINTEXT_BYTES = 20 * 1024 * 1024
_HEADER_BYTES = len(MAGIC) + SALT_BYTES + NONCE_BYTES


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or not (
        MIN_PASSPHRASE_CHARS <= len(passphrase) <= MAX_PASSPHRASE_CHARS
    ):
        raise ValueError("Passphrase must contain 12 to 1024 characters")
    return Scrypt(salt=salt, length=KEY_BYTES, n=SCRYPT_N,
                  r=SCRYPT_R, p=SCRYPT_P).derive(passphrase.encode("utf-8"))


def encrypt_backup(plaintext: bytes, passphrase: str) -> bytes:
    """Encrypt one bounded archive; neither password nor plaintext is persisted."""
    if not isinstance(plaintext, bytes) or not plaintext:
        raise ValueError("Backup content must be nonempty bytes")
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise ValueError("Backup exceeds the 20 MiB safety limit")
    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    header = MAGIC + salt + nonce
    key = _derive_key(passphrase, salt)
    return header + AESGCM(key).encrypt(nonce, plaintext, header)


def decrypt_backup(ciphertext: bytes, passphrase: str) -> bytes:
    """Authenticate and decrypt; use the same function for offline recovery."""
    if (not isinstance(ciphertext, bytes)
            or len(ciphertext) < _HEADER_BYTES + 16
            or len(ciphertext) > MAX_PLAINTEXT_BYTES + _HEADER_BYTES + 16):
        raise ValueError("Encrypted backup size is invalid")
    if not ciphertext.startswith(MAGIC):
        raise ValueError("Unsupported encrypted backup format")
    header = ciphertext[:_HEADER_BYTES]
    salt = header[len(MAGIC):len(MAGIC) + SALT_BYTES]
    nonce = header[-NONCE_BYTES:]
    try:
        plaintext = AESGCM(_derive_key(passphrase, salt)).decrypt(
            nonce, ciphertext[_HEADER_BYTES:], header)
    except (InvalidTag, ValueError, UnicodeError):
        raise ValueError("Wrong passphrase or damaged encrypted backup") from None
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise ValueError("Decrypted backup exceeds the 20 MiB safety limit")
    return plaintext


def prepare_encrypted_download(st, storage_key: str, plaintext: bytes) -> None:
    """Streamlit callback: keep only ciphertext in session state, clear password."""
    password_key = storage_key + "_passphrase"
    confirm_key = storage_key + "_confirm"
    passphrase = st.session_state.get(password_key, "")
    confirmation = st.session_state.get(confirm_key, "")
    st.session_state[storage_key + "_error"] = ""
    try:
        if not passphrase or passphrase != confirmation:
            raise ValueError("Parola alanları eşleşmiyor.")
        if len(passphrase) < MIN_PASSPHRASE_CHARS:
            raise ValueError("Parola en az 12 karakter olmalı.")
        st.session_state[storage_key + "_encrypted"] = encrypt_backup(
            plaintext, passphrase)
    except ValueError as exc:
        st.session_state[storage_key + "_encrypted"] = None
        st.session_state[storage_key + "_error"] = str(exc)
    finally:
        st.session_state[password_key] = ""
        st.session_state[confirm_key] = ""
