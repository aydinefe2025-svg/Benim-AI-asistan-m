"""Verified encrypted laboratory archive recovery into a separate PostgreSQL staging DB.

The restore capability is introduced through a test-first behavioral change.
No live database may be targeted.
"""

def restore_lab_archive(ciphertext, passphrase, *, database_url, owner_key, connect=None):
    raise NotImplementedError("isolated account laboratory restore is not implemented")
