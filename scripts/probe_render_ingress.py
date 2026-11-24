"""Offline real Caddy/Waitress ingress smoke. Test backends only; no production DB."""
import base64
import hashlib
import http.client
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.local_grant_gateway import create_gateway
from scripts.start_cano_render import commands

ROOT=pathlib.Path(__file__).resolve().parent.parent

class Store:
    def take(self,token):
        if token!="synthetic-grant":raise PermissionError()
        return {"status":"test_only"}
    def finish(self,token,result):
        raise PermissionError()

class UI(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.headers.get("Upgrade","").lower()=="websocket":
            key=self.headers["Sec-WebSocket-Key"]
            accept=base64.b64encode(hashlib.sha1((key+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.send_response(101);self.send_header("Upgrade","websocket")
            self.send_header("Connection","Upgrade");self.send_header("Sec-WebSocket-Accept",accept)
            self.end_headers();self.wfile.write(b"\x81\x02OK");self.wfile.flush()
            return
        data=json.dumps({"path":self.path,"cookie":self.headers.get("Cookie"),
                         "proto":self.headers.get("X-Forwarded-Proto")}).encode()
        self.send_response(200);self.send_header("Content-Length",str(len(data)))
        self.end_headers();self.wfile.write(data)

def serve_test():
    from waitress import serve
    serve(create_gateway({"CANO_LOCAL_GRANT_ENABLED":"1"},store=Store()),
          host="127.0.0.1",port=int(os.environ["CANO_GATEWAY_PORT"]),threads=2,
          connection_limit=20,backlog=16,channel_timeout=20,cleanup_interval=5,
          max_request_header_size=16384,max_request_body_size=65536,expose_tracebacks=False,
          trusted_proxy="127.0.0.1",trusted_proxy_headers={"x-forwarded-proto"})

def spare_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0));return s.getsockname()[1]

def run():
    ui=ThreadingHTTPServer(("127.0.0.1",0),UI)
    thread=threading.Thread(target=ui.serve_forever,daemon=True);thread.start()
    ports=[str(spare_port()),str(ui.server_port),str(spare_port())]
    assert len(set(ports))==3
    env={**os.environ,"PORT":ports[0],"CANO_STREAMLIT_PORT":ports[1],
         "CANO_GATEWAY_PORT":ports[2],"CANO_PROXY_BIND":"127.0.0.1"}
    cmds=commands(env)
    with tempfile.TemporaryFile() as log:
        workers=[]
        def request(method,path,body=None,headers=None):
            c=http.client.HTTPConnection("127.0.0.1",int(ports[0]),timeout=5)
            try:
                c.request(method,path,body=body,headers=headers or {})
                r=c.getresponse();return r.status,r.read()
            finally:c.close()
        try:
            workers.append(subprocess.Popen([sys.executable,"-m","scripts.probe_render_ingress","--test-backend"],cwd=ROOT,env=env,stdout=log,stderr=log))
            workers.append(subprocess.Popen(cmds[2],cwd=ROOT,env=env,stdout=log,stderr=log))
            for _ in range(30):
                try:
                    if request("GET","/_stcore/health")[0]==200:break
                except OSError:pass
                time.sleep(.2)
            else:raise RuntimeError("Proxy not ready")
            status,raw=request("GET","/oauth2callback?code=test",headers={"Cookie":"synthetic=1","X-Forwarded-Proto":"https"})
            v=json.loads(raw);assert status==200 and v["path"]=="/oauth2callback?code=test" and v["cookie"]=="synthetic=1" and v["proto"]=="https"
            assert request("POST","/v1/local-task/take",headers={"Authorization":"Bearer synthetic-grant"})[0]==403
            h={"X-Forwarded-Proto":"https","Authorization":"Bearer wrong"}
            assert request("POST","/v1/local-task/take",headers=h)[0]==403
            h["Authorization"]="Bearer synthetic-grant"
            assert request("POST","/v1/local-task/take",headers=h)==(200,b'{"status":"test_only"}')
            assert request("GET","/v1/local-task/take",headers=h)[0]==405
            assert request("POST","/v1/local-task/finish",body=b"x"*65537,headers={**h,"Content-Type":"application/json"})[0]==413
            with socket.create_connection(("127.0.0.1",int(ports[0])),timeout=5) as s:
                s.sendall(b"GET /_stcore/stream HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n")
                data=b""
                while b"\r\n\r\n" not in data:data+=s.recv(4096)
                head,frame=data.split(b"\r\n\r\n",1)
                assert b"101 Switching Protocols" in head
                while len(frame)<4:frame+=s.recv(4096)
                assert frame[:4]==b"\x81\x02OK"
            print("REAL_PROXY_PASS health/callback/cookie/forwarded_scheme/WebSocket_frame/HTTP_denial/wrong_grant/valid_grant/method/body_limit")
        finally:
            for p in reversed(workers):
                if p.poll() is None:p.terminate()
            for p in workers:
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            ui.shutdown();ui.server_close();thread.join()
            log.seek(0)
            if sys.exc_info()[0] is not None:print(log.read().decode(errors="replace")[-5000:])

if __name__=="__main__":
    if sys.argv[1:]==["--test-backend"]:serve_test()
    else:run()
