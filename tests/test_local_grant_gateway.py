import importlib.util
import io
import unittest
from unittest.mock import Mock

class GatewayBoundary(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("core.local_grant_gateway"),
                             "bounded gateway missing")
        from core.local_grant_gateway import create_gateway
        self.create=create_gateway
        self.store=Mock()
        self.store.take.return_value={"status":"draft"}
    def request(self,app,secure=True):
        status=[]
        env={"PATH_INFO":"/v1/local-task/take","REQUEST_METHOD":"POST",
             "HTTP_AUTHORIZATION":"Bearer test","CONTENT_LENGTH":"0",
             "wsgi.input":io.BytesIO(b""),"wsgi.url_scheme":"https" if secure else "http"}
        body=b"".join(app(env,lambda s,h:status.append(s)))
        return status[0].split()[0],body
    def test_disabled_gateway_never_accesses_store(self):
        app=self.create({},store=self.store)
        self.assertEqual(self.request(app)[0],"503")
        self.store.take.assert_not_called()
    def test_secure_scheme_required(self):
        app=self.create({"CANO_LOCAL_GRANT_ENABLED":"1"},store=self.store)
        self.assertEqual(self.request(app,False)[0],"403")
        self.store.take.assert_not_called()
        self.assertEqual(self.request(app)[0],"200")
    def test_global_rate_bound(self):
        app=self.create({"CANO_LOCAL_GRANT_ENABLED":"1"},store=self.store,max_per_minute=2)
        self.assertEqual(self.request(app)[0],"200")
        self.assertEqual(self.request(app)[0],"200")
        self.assertEqual(self.request(app)[0],"429")
        self.assertEqual(self.store.take.call_count,2)

if __name__=="__main__":unittest.main()
