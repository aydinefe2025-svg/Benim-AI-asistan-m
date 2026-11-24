"""Supervise the existing UI and bounded local worker gateway on one Render service."""
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

def serve_gateway():
    from waitress import serve
    from core.local_grant_gateway import from_environment
    port=int(os.environ.get("CANO_GATEWAY_PORT","8502"))
    serve(from_environment(),host="127.0.0.1",port=port,threads=2,
          connection_limit=20,backlog=16,channel_timeout=20,
          cleanup_interval=5,max_request_header_size=16384,
          max_request_body_size=65536,expose_tracebacks=False,
          trusted_proxy="127.0.0.1",trusted_proxy_headers={"x-forwarded-proto"})

def commands(env):
    ports=[int(env[k]) for k in ("PORT","CANO_STREAMLIT_PORT","CANO_GATEWAY_PORT")]
    if len(set(ports)) != 3 or not all(1024<=p<=65535 for p in ports):
        raise ValueError("Distinct unprivileged ports required")
    if env.get("CANO_PROXY_BIND","0.0.0.0") not in {"0.0.0.0","127.0.0.1"}:
        raise ValueError("Invalid bind")
    binary=Path(".cano-bin")/("caddy.exe" if os.name=="nt" else "caddy")
    return [
        [sys.executable,"-m","streamlit","run","app.py","--server.address","127.0.0.1",
         "--server.port",env["CANO_STREAMLIT_PORT"],"--server.headless","true"],
        [sys.executable,"-m","scripts.start_cano_render","--gateway"],
        [str(binary.resolve()),"run","--config","deploy/Caddyfile.cano","--adapter","caddyfile"]
    ]

def main():
    env=dict(os.environ)
    env.setdefault("CANO_STREAMLIT_PORT","8501")
    env.setdefault("CANO_GATEWAY_PORT","8502")
    cmds=commands(env)
    children=[]
    def stop(signum,frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        for cmd in cmds[:2]:
            children.append(subprocess.Popen(cmd,env=env))
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("Backend failed to start")
            try:
                with urllib.request.urlopen("http://127.0.0.1:"+env["CANO_STREAMLIT_PORT"]+"/_stcore/health",timeout=2) as r:
                    if r.status==200: break
            except OSError: pass
            time.sleep(0.5)
        else:
            raise RuntimeError("UI health not ready")
        children.append(subprocess.Popen(cmds[2],env=env))
        while True:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("Child exited; restart service")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(children):
            if p.poll() is None:p.terminate()
        for p in reversed(children):
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill();p.wait()

if __name__=="__main__":
    if sys.argv[1:]==["--gateway"]:serve_gateway()
    elif len(sys.argv)==1:main()
    else:raise SystemExit(2)
