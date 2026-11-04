import ast
from pathlib import Path
import re
import unittest
from unittest.mock import Mock


def load_helper(name, **namespace):
    path = Path(__file__).resolve().parents[1] / 'bot.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class BotSafetyTests(unittest.TestCase):
    def test_provider_exception_is_not_sent_to_user(self):
        answer = load_helper('yapay_zeka_yaniti', re=re, GROQ_KEY='private-token',
                             internette_ara=lambda _: '',
                             Groq=Mock(side_effect=RuntimeError('private-token and provider internals')))
        self.assertNotIn('private-token', answer('hello'))

    def test_missing_provider_key_never_calls_search_or_model(self):
        search, client = Mock(), Mock()
        answer = load_helper('yapay_zeka_yaniti', GROQ_KEY=None,
                             internette_ara=search, Groq=client)
        self.assertIn('GROQ_API_KEY', answer('hello'))
        search.assert_not_called()
        client.assert_not_called()

    def test_missing_telegram_token_prevents_polling(self):
        application = Mock()
        main = load_helper('main', TELEGRAM_TOKEN=None, GROQ_KEY='private-token', Application=application)
        with self.assertRaises(SystemExit):
            main()
        application.builder.assert_not_called()
