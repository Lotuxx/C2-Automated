import unittest
from shared.protocol import make_message, validate_message, ProtocolError

class ProtocolTests(unittest.TestCase):
    def test_valid_message(self):
        msg = make_message("PING", payload={"n": 1})
        self.assertEqual(validate_message(msg)["type"], "PING")

    def test_unknown_type_rejected(self):
        msg = make_message("PING")
        msg["type"] = "EXECUTE_SHELL"
        with self.assertRaises(ProtocolError):
            validate_message(msg)

    def test_non_object_payload_rejected(self):
        msg = make_message("PING")
        msg["payload"] = []
        with self.assertRaises(ProtocolError):
            validate_message(msg)

if __name__ == "__main__":
    unittest.main()
