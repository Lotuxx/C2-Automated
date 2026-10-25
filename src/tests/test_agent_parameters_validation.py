import unittest
from agent.main import execute_allowed

class AgentParameterValidationTests(unittest.TestCase):
    def test_rejects_non_object_parameters(self):
        for value in (None, [], "abc", 42, True):
            for command in ("echo", "get_info", "shell"):
                with self.subTest(value=value, command=command):
                    with self.assertRaisesRegex(ValueError, "parameters must be an object"):
                        execute_allowed(command, value)

    def test_rejects_shell_metacharacter_strings(self):
        for value in ("pwd; id", "whoami && echo x", "$(id)", "uname -a"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    execute_allowed("shell", {"command": value})
