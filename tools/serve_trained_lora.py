"""Bounded, loopback-only serving for the locally trained Qwen LoRA adapter.

Requires the local training runtime with torch, transformers, bitsandbytes and
peft installed, plus already-cached base weights and a candidate adapter.
"""
from __future__ import annotations

import argparse
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

MAX_BODY = 64_000
MAX_PROMPT_CHARS = 12_000
MAX_SYSTEM_CHARS = 4_000
MAX_NEW_TOKENS_DEFAULT = 256
MAX_NEW_TOKENS_LIMIT = 512
MODEL = None
TOKENIZER = None
MODEL_ID = None
ADAPTER_ID = None
GENERATION_LOCK = Lock()
BASE_SYSTEM_PROMPT = (
    "Türkçe ve doğrudan yanıt ver. Gerçekleştirmediğin araç, dosya, test veya "
    "fiziksel işlemi yapılmış gibi anlatma. Belirsizliği belirt; simülasyon ile "
    "gerçek dünya sonucunu ayır. Gizli anahtarları veya parolaları isteme ya da yazma."
)


class ExclusiveLoopbackServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def health_payload() -> dict:
    return {
        "status": "ok", "provider": "trained_local",
        "model": MODEL_ID, "adapter": ADAPTER_ID,
    }


def public_model_id(model_ref: str) -> str:
    path = Path(model_ref)
    if path.name == "qwen3-8b-training":
        return "Qwen/Qwen3-8B"
    if path.is_absolute() or str(model_ref).startswith((".", "~")):
        return path.name[:120] or "local-model"
    return str(model_ref)[:120]


def validate_budget(value: object) -> int:
    if type(value) is not int or not 32 <= value <= MAX_NEW_TOKENS_LIMIT:
        raise ValueError("invalid output budget")
    return value


class Handler(BaseHTTPRequestHandler):
    def _write(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._write(200, health_payload())
        else:
            self._write(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/generate":
            self._write(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= MAX_BODY:
                raise ValueError("invalid request size")
            data = json.loads(self.rfile.read(size))
            prompt = data.get("user_prompt", data.get("prompt"))
            system = data.get("system", "")
            budget = validate_budget(data.get("max_new_tokens", MAX_NEW_TOKENS_DEFAULT))
            if (not isinstance(prompt, str) or not prompt.strip()
                    or len(prompt) > MAX_PROMPT_CHARS
                    or not isinstance(system, str) or len(system) > MAX_SYSTEM_CHARS):
                raise ValueError("invalid prompt")
            import torch
            with GENERATION_LOCK:
                encoded = TOKENIZER.apply_chat_template(
                    [{"role": "system", "content": BASE_SYSTEM_PROMPT + "\n" + system},
                     {"role": "user", "content": prompt}],
                    tokenize=True, add_generation_prompt=True, return_tensors="pt",
                    enable_thinking=False,
                )
                input_ids = encoded["input_ids"] if hasattr(encoded, "keys") else encoded
                input_ids = input_ids.to(MODEL.get_input_embeddings().weight.device)
                with torch.inference_mode():
                    generated = MODEL.generate(
                        input_ids,
                        max_new_tokens=budget,
                        do_sample=False,
                        eos_token_id=TOKENIZER.eos_token_id,
                        pad_token_id=TOKENIZER.pad_token_id,
                    )
            answer = TOKENIZER.decode(
                generated[0, input_ids.shape[-1]:], skip_special_tokens=True
            ).strip()
            if not answer:
                raise RuntimeError("empty generation")
            self._write(200, {"provider": "trained_local", "response": answer})
        except (ValueError, TypeError, json.JSONDecodeError):
            self._write(400, {"error": "invalid request"})
        except Exception as exc:
            # Never log prompts, model output, or environment values.
            self._write(500, {"error": type(exc).__name__})

    def log_message(self, fmt, *args):
        print("local-inference " + (fmt % args).split(" ")[0], flush=True)


def main() -> None:
    global MODEL, TOKENIZER, MODEL_ID, ADAPTER_ID
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; refusing CPU inference")
    quantization = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    TOKENIZER = AutoTokenizer.from_pretrained(
        args.model, use_fast=True, local_files_only=True
    )
    if TOKENIZER.pad_token_id is None:
        TOKENIZER.pad_token = TOKENIZER.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        args.model, quantization_config=quantization, device_map="auto",
        dtype=torch.float16, attn_implementation="eager", local_files_only=True,
    )
    MODEL = PeftModel.from_pretrained(base, args.adapter).eval()
    MODEL_ID = public_model_id(args.model)
    ADAPTER_ID = Path(args.adapter).name
    print(f"Loaded local adapter; listening on 127.0.0.1:{args.port}", flush=True)
    ExclusiveLoopbackServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

