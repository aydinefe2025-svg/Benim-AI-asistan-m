"""Dependency-free security regression smoke checks for GitHub CI."""
import json
import unittest
from urllib.parse import urlsplit

def allowed_local_endpoint(url):
    try:
        u=urlsplit(url)
        return u.scheme=="http" and u.hostname in ("127.0.0.1","localhost") and u.username is None and u.password is None and u.port is not None and u.path in ("","/api/tags")
    except ValueError:
        return False

def parse_model_list(data):
    obj=json.loads(data)
    if not isinstance(obj,dict) or not isinstance(obj.get("models"),list):
        raise ValueError("Invalid Ollama response")
    names=[]
    for model in obj["models"]:
        if not isinstance(model,dict) or not isinstance(model.get("name"),str):
            raise ValueError("Invalid model entry")
        names.append(model["name"])
    return names

class SecuritySmokeTests(unittest.TestCase):
    def test_localhost(self):
        self.assertTrue(allowed_local_endpoint("http://127.0.0.1:11434/api/tags"))
        self.assertTrue(allowed_local_endpoint("http://localhost:11434/api/tags"))
    def test_external_blocked(self):
        for u in ("https://example.com:11434/api/tags","http://192.168.1.1:11434/api/tags","file:///etc/passwd","http://localhost.evil.com:11434/api/tags"):
            with self.subTest(u=u): self.assertFalse(allowed_local_endpoint(u))
    def test_credentials_blocked(self):
        self.assertFalse(allowed_local_endpoint("http://user:pass@localhost:11434/api/tags"))
    def test_invalid_port_blocked(self):
        self.assertFalse(allowed_local_endpoint("http://localhost:bad/api/tags"))
    def test_model_list(self):
        self.assertEqual(parse_model_list('{"models":[{"name":"qwen3:8b"}]}'),["qwen3:8b"])
    def test_bad_json(self):
        with self.assertRaises(json.JSONDecodeError): parse_model_list("{")
    def test_wrong_schema(self):
        for x in ('[]','{"models":{}}','{"models":[{"name":3}]}'):
            with self.subTest(x=x):
                with self.assertRaises(ValueError): parse_model_list(x)

if __name__=="__main__":
    unittest.main()
