import subprocess
import sys
import unittest

class BeaconConfigTests(unittest.TestCase):
    def test_rejects_invalid_interval(self):
        proc = subprocess.run([sys.executable, "-m", "agent.main", "--beacon-interval", "0"],
                              capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("beacon-interval", proc.stderr)

    def test_rejects_excessive_jitter(self):
        proc = subprocess.run([sys.executable, "-m", "agent.main",
                               "--beacon-interval", "10", "--beacon-jitter", "8"],
                              capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("beacon-jitter", proc.stderr)
