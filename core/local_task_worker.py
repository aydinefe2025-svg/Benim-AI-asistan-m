"""Run one explicitly exported CANO queue ticket on local Ollama only."""
import argparse
from pathlib import Path

from core.local_task_handoff import MAX_FILE_BYTES, parse_file, encode_file, run_ticket
from core.ollama_client import OllamaClient


def main():
    parser = argparse.ArgumentParser(description="CANO yerel onaylı tek görev")
    parser.add_argument("ticket", type=Path)
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.approved:
        parser.error("Yerel model çağrısını açıkça onaylamak için --approved gerekli.")
    output = args.output or args.ticket.with_suffix(".result.json")
    if output.resolve() == args.ticket.resolve():
        parser.error("Sonuç dosyası görev dosyasından farklı olmalı.")
    try:
        with args.ticket.open("rb") as file:
            ticket = parse_file(file.read(MAX_FILE_BYTES + 1))
        root = Path.home() / ".cano-local-handoff"
        root.mkdir(mode=0o700, exist_ok=True)
        client = OllamaClient("http://127.0.0.1:11434", timeout=180,
                              max_output_tokens=1200, think=False)
        def answer(goal):
            return client.chat("qwen3:8b",
                "Türkçe, somut, doğrulanmamış bir taslak ver. Kanıt yoksa belirt; "
                "araç veya deney çalıştırdığını iddia etme.", goal)
        result = run_ticket(ticket, root / "attempts.sqlite3", answer, approved=True)
        data = encode_file(result)
        try:
            with output.open("xb") as file:
                file.write(data)
        except FileExistsError:
            with output.open("rb") as file:
                if file.read(MAX_FILE_BYTES + 1) != data:
                    raise RuntimeError("Existing output differs; choose another path") from None
        print("LOCAL_DRAFT_READY: Sonuç dosyasını aynı CANO oturumuna yükleyin.")
    except Exception:
        print("LOCAL_HANDOFF_STOPPED: İş veya dosya doğrulanamadı; otomatik tekrar yok.")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
