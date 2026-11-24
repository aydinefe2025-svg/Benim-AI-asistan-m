"""Explicit one-job HTTPS worker, without automatic model or network retries."""
import argparse
import getpass
import sys
import warnings
from pathlib import Path
from core.local_grant_client import LocalGrantClient
from core.local_task_handoff import run_ticket

def run_once(client, grant, ledger_path, answer, *, approved=False):
    if approved is not True:
        raise PermissionError("Explicit local inference approval required")
    ticket = client.take(grant)
    result = run_ticket(ticket, ledger_path, answer, approved=True)
    receipt = client.finish(grant, result)
    if (not isinstance(receipt, dict) or receipt.get("id") != ticket["job_id"]
            or receipt.get("status") != "review_pending"
            or receipt.get("readback") is not True or receipt.get("verified") is not False):
        raise RuntimeError("Uncertain result receipt; do not rerun")
    return receipt

def main():
    parser = argparse.ArgumentParser(description="CANO: one approved local HTTPS task")
    parser.add_argument("--origin", required=True, help="Trusted HTTPS gateway origin")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    if not args.approved:
        parser.error("Explicit approval required (--approved)")
    if not sys.stdin.isatty():
        parser.error("Interactive terminal required for hidden grant entry")
    try:
        client = LocalGrantClient(args.origin)
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            grant = getpass.getpass("CANO tek görev yetkisi (gizli): ")
        from core.ollama_client import OllamaClient
        model = OllamaClient("http://127.0.0.1:11434", timeout=180,
                             max_output_tokens=1200, think=False)
        root = Path.home() / ".cano-local-handoff"
        root.mkdir(mode=0o700, exist_ok=True)
        def answer(goal):
            return model.chat("qwen3:8b", "Türkçe doğrulanmamış taslak. "
                              "Kanıt olmadan deney veya doğrulama iddiasında bulunma.", goal)
        run_once(client, grant, root / "attempts.sqlite3", answer, approved=True)
        print("LOCAL_DRAFT_SAVED: sonuç sunucuya kaydedildi ve geri okundu.")
    except (Exception, KeyboardInterrupt):
        print("LOCAL_HANDOFF_STOPPED: sonuç belirsiz veya yetki reddedildi. Otomatik tekrar yok.")
        raise SystemExit(2) from None

if __name__ == "__main__":
    main()
