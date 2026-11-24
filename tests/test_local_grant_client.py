import importlib.util
import unittest
from unittest.mock import Mock
class ClientBoundary(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("core.local_grant_client"),
                             "HTTPS client missing")
        from core.local_grant_client import LocalGrantClient
        self.Client=LocalGrantClient
    def test_only_https_origin_and_no_credentials_in_url(self):
        for url in ("http://example.com","https://user:pass@example.com",
                    "https://example.com/path","https://example.com?token=x",
                    "https://example.com#fragment"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):self.Client(url)
    def test_bad_grant_never_requests_network(self):
        c=self.Client("https://example.com")
        c._opener=Mock()
        with self.assertRaises(PermissionError):c.take("bad")
        c._opener.open.assert_not_called()
if __name__=="__main__":unittest.main()
