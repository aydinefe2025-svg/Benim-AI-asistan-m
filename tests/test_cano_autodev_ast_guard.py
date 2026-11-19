"""Regression: untrusted model-suggested code must not sneak dynamic execution through indirection.

These are synthetic source strings. The worker never executes generated code.
"""
import unittest

from scripts.cano_autodev_worker import validate_candidate


SOURCE = "def greeting():\n    return 'safe'\n"


class ModelDraftASTSafetyTests(unittest.TestCase):
    def test_dynamic_builtin_execution_indirection_is_rejected(self):
        examples = {
            "getattr_eval": "return getattr(__builtins__, 'eval')('40+2')",
            "globals_access": "return globals()['__builtins__']",
            "builtins_index": "return __builtins__['eval']('40+2')",
            "python_subclasses": "return (1).__class__.__mro__[1].__subclasses__()",
            "getattr_open": "return getattr(__builtins__, 'open')('/tmp/sensitive')",
            "indirect_getattribute": "return (1).__getattribute__('__class__')",
            "local_scope": "return locals()['password']",
            "reflective_vars": "return vars()['sensitive']",
        }
        for label, addition in examples.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                ValueError, "unsafe_operation_added"
            ):
                validate_candidate(SOURCE, "def greeting():\n    " + addition + "\n")

    def test_harmless_call_and_literal_change_are_still_allowed(self):
        for proposed in (
            "def greeting():\n    return 'hello there'\n",
            "def greeting():\n    return len([1, 2, 3])\n",
            "def greeting():\n    return sum([1, 2, 3])\n",
        ):
            with self.subTest(proposed=proposed):
                self.assertEqual(validate_candidate(SOURCE, proposed), proposed)


if __name__ == "__main__":
    unittest.main()
