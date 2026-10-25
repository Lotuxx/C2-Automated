import unittest
from agent.main import execute_allowed

class AgentCommandTests(unittest.TestCase):
    def test_echo(self):
        self.assertEqual(execute_allowed("echo", {"text": "lab"}), "lab")

    def test_get_info(self):
        self.assertIn("system=", execute_allowed("get_info", {}))

    def test_arbitrary_command_rejected(self):
        with self.assertRaises(ValueError):
            execute_allowed("shell", {"command": "whoami; cat /etc/shadow"})

    def test_echo_size_limited(self):
        with self.assertRaises(ValueError):
            execute_allowed("echo", {"text": "x" * 2001})

    def test_shell_allowlisted_command(self):
        self.assertTrue(execute_allowed("shell", {"command": "whoami"}))

    def test_shell_rejects_arbitrary_command(self):
        with self.assertRaises(ValueError):
            execute_allowed("shell", {"command": "whoami; cat /etc/shadow"})

    def test_shell_rejects_missing_command(self):
        with self.assertRaises(ValueError):
            execute_allowed("shell", {})

if __name__ == "__main__":
    unittest.main()
