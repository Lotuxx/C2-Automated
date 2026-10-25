"""End-to-end TLS test: sandboxed transfer tasks and dropped-session recovery."""
from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from agent.main import run as run_agent
from server.main import C2Server
from server.storage.database import Database
from shared.lab_transfer import (
    MAX_TRANSFER_BYTES, read_lab_file, validate_name, write_lab_file,
)


class TestLabFileSafety(unittest.TestCase):
    def test_upload_download_and_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/"a", Path(tmp)/"b"
            a.mkdir(); b.mkdir()
            (a/"story.txt").write_text("bonjour" ,encoding="utf-8")
            payload = read_lab_file(a, "story.txt")
            result = write_lab_file(b, payload)
            self.assertEqual(result["bytes"], len("bonjour"))
            self.assertEqual((b/"story.txt").read_text(), "bonjour")
            with self.assertRaisesRegex(ValueError, "no overwrites"):
                write_lab_file(b, payload)
            with self.assertRaisesRegex(ValueError, "integrity"):
                write_lab_file(b, {**payload, "name": "other.txt", "sha256": "0"*64})
            self.assertFalse((b/"other.txt").exists())

    def test_disallow_traversal_symlink_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for bad in ("../secret", "/etc/hosts", "a/b", "..", ".profile", "file name"):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        validate_name(bad)
            (root/"large.bin").write_bytes(b"x"*(MAX_TRANSFER_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "128 KiB"):
                read_lab_file(root, "large.bin")
            (root/"link.txt").symlink_to(root/"large.bin")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                read_lab_file(root, "link.txt")


class TestRealTLSTransfers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="c2-tls-integration-")
        self.root = Path(self.tmp.name)
        self.ca = self.root/"server.crt"
        self.key = self.root/"server.key"
        try:
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-days", "1",
                "-nodes", "-keyout", str(self.key), "-out", str(self.ca),
                "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
            ], capture_output=True, check=True, timeout=15)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            self.skipTest(f"openssl not available: {exc}")

        self.agent_id = str(uuid.uuid4())
        self.server_upload = self.root/"server_files"
        self.server_download = self.root/"server_downloads"
        self.agent_files = self.root/"agent_files"
        for path in (self.server_upload, self.server_download, self.agent_files):
            path.mkdir()
        self.db = Database(":memory:")
        await self.db.initialize()
        self.app = C2Server(self.db, upload_dir=self.server_upload,
                            download_dir=self.server_download)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(self.ca), str(self.key))
        self.listener = await asyncio.start_server(self.app._tracked_handle_client,
                                                   "127.0.0.1", 0, ssl=tls)
        self.port = self.listener.sockets[0].getsockname()[1]
        args = argparse.Namespace(
            server="127.0.0.1", port=self.port, ca=str(self.ca),
            agent_id=self.agent_id, lab_dir=str(self.agent_files),
            beacon_interval=1.0, beacon_jitter=0.0,
            reconnect_sessions=2, reconnect_attempts=5, reconnect_max_delay=0.2,
        )
        self.agent_task = asyncio.create_task(run_agent(args))
        await self.wait_for(lambda: self.agent_id in self.app.connections)
        await self.wait_for(lambda: any(s["state"] == "ACTIVE" for s in self._sessions_cache),
                            refresh=self._refresh_sessions)

    async def asyncTearDown(self):
        self.agent_task.cancel()
        await asyncio.gather(self.agent_task, return_exceptions=True)
        await self.app.shutdown()
        self.listener.close()
        await self.listener.wait_closed()
        await self.db.close()
        self.tmp.cleanup()

    _sessions_cache = []

    async def _refresh_sessions(self):
        self._sessions_cache = await self.db.list_sessions()

    async def wait_for(self, check, *, refresh=None, timeout=4.0):
        async def poll():
            while True:
                if refresh:
                    await refresh()
                if check():
                    return
                await asyncio.sleep(0.025)
        await asyncio.wait_for(poll(), timeout)

    async def wait_completed(self, tid):
        async def task_completed():
            row = await self.db.get_task(tid)
            return row["status"] if row else None
        async def poll():
            for _ in range(160):
                status = await task_completed()
                if status in {"COMPLETED", "FAILED", "CANCELLED"}:
                    return status
                await asyncio.sleep(0.025)
        return await asyncio.wait_for(poll(), 5)

    async def test_two_agents_have_separate_lab_file_workspaces(self):
        second_id = str(uuid.uuid4())
        second_dir = self.root / "second_agent_files"
        second_dir.mkdir()
        args = argparse.Namespace(
            server="127.0.0.1", port=self.port, ca=str(self.ca),
            agent_id=second_id, lab_dir=str(second_dir),
            beacon_interval=1.0, beacon_jitter=0.0,
            reconnect_sessions=0, reconnect_attempts=5, reconnect_max_delay=0.2,
        )
        second_task = asyncio.create_task(run_agent(args))
        try:
            await self.wait_for(lambda: second_id in self.app.connections)
            (self.server_upload / "first.txt").write_text("for first")
            (self.server_upload / "second.txt").write_text("for second")
            tid1 = await self.app.dispatch_task(
                self.agent_id, "upload", read_lab_file(self.server_upload, "first.txt"))
            # The second agent may have registered but not yet synchronized.
            await self.wait_for(lambda: second_id not in self.app.pending_sync)
            tid2 = await self.app.dispatch_task(
                second_id, "upload", read_lab_file(self.server_upload, "second.txt"))
            self.assertEqual(await self.wait_completed(tid1), "COMPLETED")
            self.assertEqual(await self.wait_completed(tid2), "COMPLETED")
            self.assertEqual((self.agent_files / "first.txt").read_text(), "for first")
            self.assertEqual((second_dir / "second.txt").read_text(), "for second")
            self.assertFalse((self.agent_files / "second.txt").exists())
            self.assertFalse((second_dir / "first.txt").exists())
        finally:
            second_task.cancel()
            await asyncio.gather(second_task, return_exceptions=True)

    async def test_disconnect_cli_triggers_fresh_session(self):
        import unittest.mock
        old_writer = self.app.connections[self.agent_id]
        old_sessions = await self.db.list_sessions()
        old_id = old_sessions[0]["session_id"]
        inputs = iter([f"disconnect {self.agent_id[:8]}", "quit"])

        async def fake_input(*args, **kwargs):
            return next(inputs)

        with unittest.mock.patch("server.main.asyncio.to_thread", side_effect=fake_input):
            await self.app.cli()
        await self.wait_for(lambda: self.agent_id in self.app.connections and
                            self.app.connections[self.agent_id] is not old_writer, timeout=5)
        await self.wait_for(lambda: any(
            entry["session_id"] != old_id and entry["state"] == "ACTIVE"
            for entry in self._sessions_cache), refresh=self._refresh_sessions)
        sessions = await self.db.list_sessions()
        self.assertNotEqual(sessions[0]["session_id"], old_id)
        self.assertEqual(sessions[0]["state"], "ACTIVE")
        self.assertTrue(any(s["session_id"] == old_id and
                            s["state"] == "DISCONNECTED" for s in sessions))

    async def test_transfer_and_reconnect_on_real_tls(self):
        (self.server_upload/"hello.txt").write_text("real TLS transfer!", encoding="utf-8")
        tid = await self.app.dispatch_task(
            self.agent_id, "upload", read_lab_file(self.server_upload, "hello.txt"))
        self.assertEqual(await self.wait_completed(tid), "COMPLETED")
        self.assertEqual((self.agent_files/"hello.txt").read_text(), "real TLS transfer!")

        tid2 = await self.app.dispatch_task(self.agent_id, "download", {"name": "hello.txt"})
        self.assertEqual(await self.wait_completed(tid2), "COMPLETED")
        self.assertEqual((self.server_download/"hello.txt").read_text(), "real TLS transfer!")
        old_sessions = await self.db.list_sessions()
        old_session = old_sessions[0]["session_id"]
        writer = self.app.connections[self.agent_id]
        writer.close()  # deliberate drop of an established TLS connection
        await self.wait_for(lambda: self.agent_id in self.app.connections and
                            self.app.connections[self.agent_id] is not writer, timeout=5)
        await self.wait_for(lambda: any(
            entry["session_id"] != old_session and entry["state"] == "ACTIVE"
            for entry in self._sessions_cache), refresh=self._refresh_sessions)
        sessions = await self.db.list_sessions()
        self.assertNotEqual(sessions[0]["session_id"], old_session)
        self.assertEqual(sessions[0]["agent_id"], self.agent_id)
        self.assertTrue(any(s["session_id"] == old_session and
                            s["state"] == "DISCONNECTED" for s in sessions))
        # Reject requests attempting traversal even if bypassing CLI validation.
        bad = await self.app.dispatch_task(self.agent_id, "download", {"name": "../nope"})
        self.assertEqual(await self.wait_completed(bad), "FAILED")
        self.assertFalse((self.server_download/"nope").exists())
        tid3 = await self.app.dispatch_task(self.agent_id, "echo", {"text": "after reconnect"})
        self.assertEqual(await self.wait_completed(tid3), "COMPLETED")
        results = await self.db.list_results(tid3)
        self.assertEqual(results[0]["output"], "after reconnect")

class TestRemoteTransferCLI(unittest.IsolatedAsyncioTestCase):
    async def test_cli_upload_is_real_agent_task_not_lab_demo(self):
        import unittest.mock
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"go.txt").write_text("from-server", encoding="utf-8")
            db = Database(":memory:")
            await db.initialize()
            server = C2Server(db, upload_dir=root, download_dir=root)
            agent_id = "abababab-1111-1111-1111-111111111111"
            await db.upsert_agent(agent_id, "testhost", "Linux")
            writer = unittest.mock.MagicMock()
            writer.is_closing.return_value = False
            writer.drain = unittest.mock.AsyncMock()
            server.connections[agent_id] = writer
            inputs = iter(["task abababab upload go.txt", "quit"])
            async def fake_input(*args, **kwargs):
                return next(inputs)
            with unittest.mock.patch("server.main.asyncio.to_thread", side_effect=fake_input):
                await server.cli()
            self.assertEqual(len(writer.write.call_args_list), 1)
            raw = writer.write.call_args_list[0].args[0]
            message = json.loads(raw)
            self.assertEqual(message["type"], "TASK")
            self.assertEqual(message["payload"]["command"], "upload")
            self.assertEqual(message["payload"]["parameters"]["name"], "go.txt")
            tasks = await db.list_tasks()
            self.assertEqual(tasks[0]["status"], "WAITING_ACK")
            await db.close()
