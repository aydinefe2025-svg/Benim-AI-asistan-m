import importlib.util
import io
import json
import unittest
from unittest.mock import Mock

class TransportBoundary(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("core.local_grant_http"),
                             "Bounded HTTP adapter missing")
        from core.local_grant_http import make_app
        self.store=Mock()
        self.app=make_app(self.store)
    def request(self,path="/v1/local-task/take",method="POST",token="grant",body=b"",length=None,query=""):
        status=[]
        def start(s,headers):status.extend([s,dict(headers)])
        env={"PATH_INFO":path,"REQUEST_METHOD":method,"QUERY_STRING":query,
             "HTTP_AUTHORIZATION":"Bearer "+token,"CONTENT_LENGTH":str(len(body) if length is None else length),
             "CONTENT_TYPE":"application/json","wsgi.input":io.BytesIO(body)}
        payload=b"".join(self.app(env,start))
        self.assertEqual(status[1]["Cache-Control"],"no-store")
        return int(status[0].split()[0]),json.loads(payload)
    def test_only_two_explicit_routes_and_methods(self):
        self.store.take.return_value={"job_id":"sample"}
        self.assertEqual(self.request(),(200,{"job_id":"sample"}))
        self.store.take.assert_called_once_with("grant")
        self.assertEqual(self.request(method="GET")[0],405)
        self.assertEqual(self.request(path="/v1/local-task/issue")[0],404)
        self.assertEqual(self.request(query="token=secret")[0],400)
    def test_bounded_json_and_generic_errors(self):
        self.assertEqual(self.request(path="/v1/local-task/finish",length=65537)[0],413)
        self.assertEqual(self.request(path="/v1/local-task/finish",body=b"{")[0],400)
        self.store.finish.assert_not_called()
        self.store.finish.side_effect=RuntimeError("private DB connection detail")
        code,result=self.request(path="/v1/local-task/finish",body=b'{"draft":"x"}')
        self.assertEqual(code,503)
        self.assertNotIn("private",str(result))
    def test_no_bearer_and_wrong_grant(self):
        self.assertEqual(self.request(token="")[0],403)
        self.store.take.assert_not_called()
        self.store.take.side_effect=PermissionError("private job")
        self.assertEqual(self.request(),(403,{"error":"denied"}))

if __name__=="__main__":unittest.main()
