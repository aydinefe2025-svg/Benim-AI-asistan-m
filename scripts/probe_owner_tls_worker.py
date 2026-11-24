"""Disposable TLS proof on loopback with a private test CA and real Ollama.
No public listener; no production data; the test key is deleted on exit.
The store is the in-memory single-task prototype; PostgreSQL is tested separately.
"""
import hashlib
import json
import pathlib
import secrets
import ssl
import subprocess
import tempfile
import threading
import time
import uuid
from wsgiref.simple_server import make_server, WSGIRequestHandler
from core.authorized_queue import AuthorizedQueue
from core.local_task_handoff import claim_ticket, run_ticket, encode_file
from core.local_single_grant import SingleTaskGrant
from core.local_grant_gateway import create_gateway
from core.local_grant_worker import run_once
from core.local_grant_client import LocalGrantClient
from core.ollama_client import OllamaClient

def run(root):
    root.mkdir()
    q=AuthorizedQueue(root/"queue.db",owner_key="synthetic-owner")
    job=q.enqueue("tls","12 çarpı 7 işleminin sonucunu yalnızca rakamla yaz.",approved=True)
    private=claim_ticket(q,approved=True)
    grant,inner=SingleTaskGrant.issue(q,private,approved=True)
    token=job["id"]+"."+secrets.token_hex(32)
    class Store:
        def take(self,value):
            if not secrets.compare_digest(value,token):raise PermissionError()
            return grant.take(inner)
        def finish(self,value,result):
            if not secrets.compare_digest(value,token):raise PermissionError()
            return grant.finish(inner,result)
    class Quiet(WSGIRequestHandler):
        def log_message(self,*args):pass
        def get_environ(self):
            env=super().get_environ();env["HTTPS"]="on";return env
    with tempfile.TemporaryDirectory() as temp:
        temp=pathlib.Path(temp)
        cert=temp/"test.pem";key=temp/"test.key"
        openssl=pathlib.Path("C:/Program Files/Git/usr/bin/openssl.exe")
        if not openssl.is_file():raise RuntimeError("Test OpenSSL not available")
        a=subprocess.run([str(openssl),"req","-x509","-newkey","rsa:2048","-nodes",
                          "-keyout",str(key),"-out",str(cert),"-days","1",
                          "-subj","/CN=localhost","-addext","subjectAltName=DNS:localhost,IP:127.0.0.1"],
                         capture_output=True,timeout=20)
        if a.returncode:raise RuntimeError("Ephemeral TLS fixture failed")
        server=make_server("127.0.0.1",0,create_gateway({"CANO_LOCAL_GRANT_ENABLED":"1"},store=Store()),handler_class=Quiet)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version=ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert,key)
        server.socket=ctx.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        start=time.monotonic()
        try:
            origin="https://127.0.0.1:"+str(server.server_port)
            try:
                LocalGrantClient(origin).take(token)
                raise AssertionError("Untrusted certificate accepted")
            except RuntimeError:pass
            client=LocalGrantClient(origin,ca_file=str(cert))
            try:
                client.take(job["id"]+"."+"0"*64)
                raise AssertionError("Wrong token accepted")
            except PermissionError:pass
            model=OllamaClient("http://127.0.0.1:11434",timeout=90,max_output_tokens=256,think=False)
            calls=[]
            def answer(goal):
                calls.append(goal)
                return model.chat("qwen3:8b","Yalnızca istenen sayıyı yaz, başka metin ekleme.",goal)
            receipt=run_once(client,token,root/"ledger.db",answer,approved=True)
            try:
                client.take(token)
                raise AssertionError("Duplicate task retrieval accepted")
            except PermissionError:pass
            saved=AuthorizedQueue(root/"queue.db",owner_key="synthetic-owner").get(job["id"])
            assert receipt["readback"] and not receipt["verified"] and saved["attempts"]==1
            assert saved["state"]=="review_pending" and len(calls)==1 and saved["draft"].strip()=="84"
            summary={"scope":"new bounded gateway + new run_once worker, real loopback TLS and Ollama; isolated SQLite grant; PG independent",
                     "untrusted_certificate_denied":True,"wrong_token_denied":True,"duplicate_take_denied":True,
                     "https_only":True,"model_calls":len(calls),"attempts":saved["attempts"],
                     "state":saved["state"],"readback":True,"verified":False,
                     "elapsed_s":round(time.monotonic()-start,2),"draft":saved["draft"]}
            raw=encode_file(summary);(root/"receipt.json").write_bytes(raw)
            print(json.dumps(summary,ensure_ascii=True));print("RECEIPT_SHA256",hashlib.sha256(raw).hexdigest())
        finally:
            server.shutdown();server.server_close();thread.join()
    print("EPHEMERAL_TLS_KEY_REMOVED",not key.exists())

if __name__=="__main__":
    run(pathlib.Path(__file__).resolve().parent.parent/("OWNER_TLS_PROBE_"+uuid.uuid4().hex[:8]))
