"""Safe, fully local installer/uninstaller regression coverage."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent.local_install import InstallationError, install, uninstall


class LocalAgentInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="installer-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "pa-agent-lab-test"

    def test_install_preview_then_uninstall_removes_entire_program(self):
        install(self.root)
        installed = list(self.root.rglob("*.py"))
        self.assertGreaterEqual(len(installed), 6)
        before = uninstall(self.root, execute=False)
        self.assertIn("agent/main.py", before)
        self.assertTrue(self.root.exists())
        removed = uninstall(self.root, execute=True)
        self.assertEqual(before, removed)
        self.assertFalse(self.root.exists())
        self.assertTrue(Path(self.tmp.name).exists())

    def test_installed_copy_is_usable_and_caches_are_cleaned(self):
        install(self.root)
        process = subprocess.run(
            [sys.executable, "-m", "agent.main", "--help"],
            cwd=self.root, text=True, capture_output=True,
            check=False, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--beacon-interval", process.stdout)
        result = uninstall(self.root, execute=True)
        self.assertTrue(any("__pycache__" in x for x in result))
        self.assertFalse(self.root.exists())

    def test_refuses_unmanaged_files_in_installed_directory(self):
        install(self.root)
        (self.root / "my_notes.txt").write_text("do not remove me", encoding="utf-8")
        with self.assertRaisesRegex(InstallationError, "unknown file"):
            uninstall(self.root, execute=True)
        self.assertTrue((self.root / "agent/main.py").exists())
        self.assertTrue((self.root / "my_notes.txt").exists())

    def test_refuses_symlinks(self):
        install(self.root)
        external = Path(self.tmp.name) / "external.txt"
        external.write_text("never delete", encoding="utf-8")
        (self.root / "agent" / "linked.txt").symlink_to(external)
        with self.assertRaisesRegex(InstallationError, "symlink"):
            uninstall(self.root, execute=True)
        self.assertTrue(external.exists())
        self.assertTrue((self.root / "agent/main.py").exists())

    def test_refuses_tampered_manifest(self):
        install(self.root)
        manifest_path = self.root / ".pa-agent-lab-install.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["target"] = "/somewhere/else"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(InstallationError, "manifest does not match"):
            uninstall(self.root, execute=True)
        self.assertTrue(self.root.exists())

    def test_refuses_wrong_target_name(self):
        root = Path(self.tmp.name) / "unrelated_project"
        with self.assertRaisesRegex(InstallationError, "folder name"):
            install(root)
        self.assertFalse(root.exists())

    def test_refuses_existing_directory_before_installing(self):
        self.root.mkdir()
        (self.root / "user-file.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(InstallationError, "already exist"):
            install(self.root)
        self.assertTrue((self.root / "user-file.txt").exists())

    def test_cli_is_dry_run_by_default(self):
        install(self.root)
        proc = subprocess.run(
            [sys.executable, "-m", "agent.local_install", "uninstall",
             "--target", str(self.root)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("DRY RUN", proc.stdout)
        self.assertTrue(self.root.exists())
        proc2 = subprocess.run(
            [sys.executable, "-m", "agent.local_install", "uninstall",
             "--target", str(self.root), "--execute"],
            text=True, capture_output=True)
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertIn("UNINSTALLED", proc2.stdout)
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()

class AdditionalRemovalGuards(unittest.TestCase):
    def test_unknown_bytecode_is_not_deleted(self):
        from agent.local_install import InstallationError, install, uninstall
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pa-agent-lab-test"
            install(root)
            cache = root / "agent" / "__pycache__"
            cache.mkdir()
            (cache / "unknown.cpython-313.pyc").write_bytes(b"do not delete")
            with self.assertRaisesRegex(InstallationError, "unknown file"):
                uninstall(root, execute=True)
            self.assertTrue((root / "agent/main.py").exists())

    def test_unknown_directory_prevents_uninstall(self):
        from agent.local_install import InstallationError, install, uninstall
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pa-agent-lab-test"
            install(root)
            (root / "data").mkdir()
            (root / "data" / "personal.txt").write_text("keep")
            with self.assertRaisesRegex(InstallationError, "unrecognized directory"):
                uninstall(root, execute=True)
            self.assertTrue((root / "data/personal.txt").exists())
