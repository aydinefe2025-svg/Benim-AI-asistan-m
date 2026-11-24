"""Loopback-only proof of the proposed single-task HTTP transport.
Not a public service or a persistent daemon. No tokens logged.
"""
import json, time, threading, urllib.request, urllib.error, hashlib, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from core.authorized_queue import AuthorizedQueue
from core.local_task_handoff import claim_ticket, run_ticket, parse_file, encode_file
from core.local_single_grant import SingleTaskGrant
from core.ollama_client import OllamaClient

def run(root):
    root.mkdir()
    q=AuthorizedQueue(root/"queue.db",owner_key="synthetic-owner")
    job=q.enqueue("one", "12 çarpı 7 ve ters işlem sonucunu tek cümlede yaz.",approved=True)
    private=claim_ticket(q,approved=True)
    grant,token=SingleTaskGrant.issue(q,private,approved=True)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,data):
            payload=encode_file(data)
            self.send_response(status);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)));self.send_header("Cache-Control","no-store")
            self.end_headers();self.wfile.write(payload)
        def do_POST(self):
            try:
                auth=self.headers.get("Authorization","")
                if not auth.startswith("Bearer "):raise PermissionError()
                n=int(self.headers.get("Content-Length","0"))
                if not 0<=n<=65536:raise ValueError()
                raw=self.rfile.read(n)
                if self.path=="/take" and not raw:
                    data=grant.take(auth[7:])
                elif self.path=="/finish" and raw:
                    data=grant.finish(auth[7:],parse_file(raw))
                else:
                    self.reply(404,{"error":"not_found"});return
                self.reply(200,data)
            except PermissionError:self.reply(403,{"error":"denied"})
            except (ValueError,KeyError):self.reply(400,{"error":"invalid"})
            except Exception:self.reply(503,{"error":"uncertain"})
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    base="http://127.0.0.1:"+str(server.server_port)
    def post(path,auth,data=None):
        r=urllib.request.Request(base+path,data=b"" if data is None else encode_file(data),
             headers={"Authorization":"Bearer "+auth,"Content-Type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(r,timeout=10) as f:return f.status,parse_file(f.read(65537))
        except urllib.error.HTTPError as e:return e.code,parse_file(e.read(65537))
    start=time.monotonic();calls=[]
    try:
        assert post("/take","wrong")[0]==403
        code,ticket=post("/take",token);assert code==200
        assert post("/take",token)[0]==403
        assert "owner_key" not in ticket and "lease_token" not in ticket
        model=OllamaClient("http://127.0.0.1:11434",timeout=90,max_output_tokens=256,think=False)
        def answer(goal):
            calls.append(goal)
            return model.chat("qwen3:8b","Kısa Türkçe yanıt; sonucu ve ters işlemi göster.",goal)
        result=run_ticket(ticket,root/"ledger.db",answer,approved=True)
        assert post("/finish","wrong",result)[0]==403
        bad=dict(result,job_id="0"*32);assert post("/finish",token,bad)[0]==400
        code,receipt=post("/finish",token,result);assert code==200 and receipt["readback"]
        assert post("/finish",token,result)==(200,receipt)
        grant.revoke();assert post("/finish",token,result)[0]==403
        saved=AuthorizedQueue(root/"queue.db",owner_key="synthetic-owner").get(job["id"])
        assert saved["state"]=="review_pending" and saved["attempts"]==1 and len(calls)==1 and "84" in saved["draft"]
        summary={"scope":"loopback HTTP prototype, isolated SQLite, actual Ollama; not production",
                 "model_calls":len(calls),"state":saved["state"],"attempts":saved["attempts"],
                 "wrong_token_denied":True,"duplicate_take_denied":True,"wrong_job_denied":True,
                 "same_result_replay_readback":True,"revoked_denied":True,"verified":False,
                 "draft":saved["draft"],"elapsed_s":round(time.monotonic()-start,2)}
        data=encode_file(summary);(root/"receipt.json").write_bytes(data)
        print(json.dumps(summary,ensure_ascii=True));print("RECEIPT_SHA256",hashlib.sha256(data).hexdigest())
    finally:
        server.shutdown();server.server_close();t.join()

if __name__=="__main__":
    run(Path(__file__).resolve().parent.parent/("HTTP_PROBE_"+uuid.uuid4().hex[:8]))
