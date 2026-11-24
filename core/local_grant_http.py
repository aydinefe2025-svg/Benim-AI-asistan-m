"""Restricted WSGI transport for existing one-task grants.

An HTTPS reverse proxy with request/header/time/rate limits must terminate
TLS before routing ONLY these two paths here. No grant issuance, generic
queue access, browser session handling, or public listener in this module.
Do not log Authorization headers or request bodies.
"""
from http import HTTPStatus
from core.local_task_handoff import MAX_FILE_BYTES, parse_file, encode_file

_TAKE = "/v1/local-task/take"
_FINISH = "/v1/local-task/finish"


def make_app(store):
    def application(env, start_response):
        def reply(status, obj):
            body = encode_file(obj)
            start_response(f"{status} {HTTPStatus(status).phrase}", [
                ("Content-Type","application/json; charset=utf-8"),
                ("Cache-Control","no-store"),("X-Content-Type-Options","nosniff"),
                ("Content-Length",str(len(body)))])
            return [body]
        path = env.get("PATH_INFO")
        if path not in (_TAKE,_FINISH):
            return reply(404,{"error":"not_found"})
        if env.get("REQUEST_METHOD") != "POST":
            return reply(405,{"error":"method_not_allowed"})
        if env.get("QUERY_STRING"):
            return reply(400,{"error":"query_not_allowed"})
        auth = env.get("HTTP_AUTHORIZATION","")
        if not auth.startswith("Bearer ") or not 1 <= len(auth[7:]) <= 128:
            return reply(403,{"error":"denied"})
        try:
            size = int(env.get("CONTENT_LENGTH") or "0")
        except (ValueError,TypeError):
            return reply(400,{"error":"invalid_length"})
        if size > MAX_FILE_BYTES:
            return reply(413,{"error":"too_large"})
        if size < 0 or (path == _TAKE and size != 0):
            return reply(400,{"error":"invalid_length"})
        if path == _FINISH and (size == 0 or env.get("CONTENT_TYPE","").split(";")[0].strip()!="application/json"):
            return reply(400,{"error":"invalid_body"})
        try:
            if path == _TAKE:
                result = store.take(auth[7:])
            else:
                raw = env["wsgi.input"].read(size)
                if len(raw) != size:
                    return reply(400,{"error":"invalid_body"})
                result = store.finish(auth[7:],parse_file(raw))
            return reply(200,result)
        except PermissionError:
            return reply(403,{"error":"denied"})
        except (ValueError,KeyError,TypeError):
            return reply(400,{"error":"invalid"})
        except Exception:
            return reply(503,{"error":"uncertain"})
    return application
