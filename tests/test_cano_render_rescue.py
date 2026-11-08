import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

SPEC = importlib.util.spec_from_file_location("cano_render_rescue", Path(__file__).with_name("cano_render_rescue.py"))
rescue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rescue)


def source_uri(db="research_library_persistent_db", host="dpg-synthetic.frankfurt-postgres.render.com", extra=""):
    return f"postgresql://reader:secret@{host}/{db}{extra}"


def test_rejects_temp_directory(tmp_path):
    with pytest.raises(rescue.RescueRefused, match="temporary"):
        rescue.check_operator_environment(tmp_path, repo_root=Path("/other/repo"))


def test_rejects_render_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(rescue.RescueRefused, match="ephemeral"):
        rescue.check_operator_environment(tmp_path, repo_root=Path("/other/repo"))


def test_rejects_wrong_database_and_plaintext_remote():
    for url in (source_uri(db="assistant_pg"), source_uri(host="malicious.example.com"),
                source_uri(extra="?sslmode=disable")):
        with pytest.raises(rescue.RescueRefused):
            rescue.check_render_source(url)


def test_preflight_has_no_prompt_or_connection(monkeypatch, tmp_path):
    monkeypatch.setattr(rescue, "check_operator_environment", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(rescue, "check_postgres_client", lambda: "/bin/pg_dump")
    result = rescue.run(tmp_path, preflight=True, confirm_storage=False,
                        prompt=lambda *_: pytest.fail("prompted during preflight"))
    assert result["preflight"] == "PASS" and result["archive_created"] is False


def test_run_requires_manual_storage_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(rescue, "check_operator_environment", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(rescue, "check_postgres_client", lambda: "/bin/pg_dump")
    with pytest.raises(rescue.RescueRefused, match="confirm-independent-storage"):
        rescue.run(tmp_path, preflight=False, confirm_storage=False,
                   prompt=lambda *_: pytest.fail("prompt before explicit confirmation"))


def test_backup_verifies_and_leaves_no_secrets_in_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(rescue, "check_operator_environment", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(rescue, "check_postgres_client", lambda: "/bin/pg_dump")
    module = ModuleType("scripts.cano_encrypted_backup")
    calls = []
    def backup(dest, **kw):
        calls.append(("backup", dest, dict(kw)))
        assert os.environ[rescue._DB_ENV] == source_uri()
        assert os.environ[rescue._KEY_ENV] == "a" * 64
        return {"receipt": "/proof.receipt.json", "archive": "/proof.canoenc", "archive_sha256": "xyz"}
    def verify(receipt, **kw):
        calls.append(("verify", str(receipt), dict(kw)))
        return {"archive_sha256": "xyz"}
    module.make_encrypted_backup = backup
    module.verify_encrypted_backup = verify
    parent = ModuleType("scripts")
    monkeypatch.setitem(sys.modules, "scripts", parent)
    monkeypatch.setitem(sys.modules, "scripts.cano_encrypted_backup", module)
    monkeypatch.setenv(rescue._DB_ENV, "prior-url")
    monkeypatch.delenv(rescue._KEY_ENV, raising=False)
    values = iter((source_uri(), "a" * 64))
    result = rescue.run(tmp_path, preflight=False, confirm_storage=True,
                        prompt=lambda *_: next(values))
    assert [x[0] for x in calls] == ["backup", "verify"]
    assert result["cryptographic_verification"] == "PASS"
    assert result["independent_location_verified"] is False
    assert result["restored_to_isolated_database"] is False
    assert os.environ[rescue._DB_ENV] == "prior-url"
    assert rescue._KEY_ENV not in os.environ


def test_wrong_key_never_calls_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(rescue, "check_operator_environment", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(rescue, "check_postgres_client", lambda: "/bin/pg_dump")
    values = iter((source_uri(), "not-a-key"))
    with pytest.raises(rescue.RescueRefused, match="256-bit"):
        rescue.run(tmp_path, preflight=False, confirm_storage=True,
                   prompt=lambda *_: next(values))


def test_interactive_secret_prompt_refuses_when_terminal_is_not_private(monkeypatch):
    class InsecureInput:
        def isatty(self): return False
    monkeypatch.setattr(sys, "stdin", InsecureInput())
    with pytest.raises(rescue.RescueRefused, match="interactive terminal"):
        rescue.secure_prompt("Secret: ")