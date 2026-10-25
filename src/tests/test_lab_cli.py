import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab_demo.cli import run_lab_command

class LabCliTests(unittest.TestCase):
    def test_cli_flow(self):
        with tempfile.TemporaryDirectory() as d, patch('lab_demo.cli.WORKSPACE', Path(d)):
            self.assertIn('LOCAL', run_lab_command(['help']))
            self.assertIn('Initialized', run_lab_command(['init']))
            self.assertIn('simulated upload', run_lab_command(['upload']))
            self.assertIn('simulated download', run_lab_command(['download']))
            self.assertIn('simulated check-in', run_lab_command(['beacon']))
            self.assertIn('MANIFEST ONLY', run_lab_command(['persist']))
            self.assertIn('cleanup ONLY', run_lab_command(['self_destruct']))
            self.assertIn('error', run_lab_command(['self_destruct']))
