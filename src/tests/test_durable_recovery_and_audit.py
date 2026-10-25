"""Durable uncertainty recording and broader end-to-end TLS feature regression."""
import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from server.storage.database import Database
from server.main import C2Server
from agent.main import execute_allowed
from tests.test_remote_transfer_reconnect import TestRealTLSTransfers


class TestRestartLedger(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pa-durable-")
        self.path = Path(self.tmp.name) / "persistent.sqlite3"
        self.db = Database(str(self.path))
        await self.db.initialize()
        self.agent = str(uuid.uuid4())
        await self.db.upsert_agent(self.agent, "lab", "Linux")

    async def asyncTearDown(self):
        if self.db.conn is not None:
            await self.db.close()
        self.tmp.cleanup()

    async def _create_in_state(self, state: str, command="get_info"):
        tid = str(uuid.uuid4())
        await self.db.create_task(tid, self.agent, command, {}, "PENDING")
        for next_state in {
            "PENDING": (),
            "WAITING_ACK": ("WAITING_ACK",),
            "QUEUED": ("WAITING_ACK", "QUEUED"),
            "RUNNING": ("WAITING_ACK", "QUEUED", "RUNNING"),
            "COMPLETED": ("WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED"),
        }[state]:
            if next_state == "COMPLETED":
                await self.db.complete_task_with_result(tid, "COMPLETED", str(uuid.uuid4()), self.agent, "done")
            else:
                await self.db.update_task_status(tid, next_state)
        return tid

    async def test_crash_then_restart_preserves_uncertainty_and_results(self):
        ids = {state: await self._create_in_state(state) for state in
               ("PENDING", "WAITING_ACK", "QUEUED", "RUNNING", "COMPLETED")}
        await self.db.create_session(str(uuid.uuid4()), self.agent, "ACTIVE")
        await self.db.close()
        self.db = Database(str(self.path))
        await self.db.initialize()
        self.assertEqual(await self.db.reconcile_process_restart(), 4)
        records = {row["task_id"]: row for row in await self.db.list_interruptions()}
        self.assertEqual(len(records), 4)
        for state, tid in ids.items():
            status = (await self.db.get_task(tid))["status"]
            if state == "COMPLETED":
                self.assertEqual(status, "COMPLETED")
                self.assertEqual(len(await self.db.list_results(tid)), 1)
                self.assertNotIn(tid, records)
            else:
                self.assertEqual(records[tid]["previous_status"], state)
                self.assertEqual(records[tid]["reason"], "server_restart")
                self.assertEqual(status, "FAILED" if state == "RUNNING" else "CANCELLED")
                expected = "NOT_SENT" if state == "PENDING" else "UNKNOWN_OUTCOME"
                self.assertEqual(records[tid]["outcome"], expected)
        self.assertEqual((await self.db.list_sessions())[0]["state"], "DISCONNECTED")
        self.assertEqual(await self.db.reconcile_process_restart(), 0)
        self.assertEqual(len(await self.db.list_interruptions()), 4)

    async def test_interruption_is_atomic_and_not_duplicated(self):
        tid = await self._create_in_state("QUEUED")
        self.assertTrue(await self.db.interrupt_task(tid, "connection_lost"))
        self.assertFalse(await self.db.interrupt_task(tid, "connection_lost"))
        info = await self.db.get_interruption(tid)
        self.assertEqual(info["reason"], "connection_lost")
        self.assertEqual(info["outcome"], "UNKNOWN_OUTCOME")
        self.assertEqual((await self.db.get_task(tid))["status"], "CANCELLED")

    async def test_retries_recorded_once(self):
        tid = await self._create_in_state("RUNNING")
        await self.db.interrupt_task(tid, "connection_lost")
        new_tid = str(uuid.uuid4())
        self.assertTrue(await self.db.mark_retried(tid, new_tid))
        self.assertFalse(await self.db.mark_retried(tid, str(uuid.uuid4())))
        await self.db.close()
        self.db = Database(str(self.path))
        await self.db.initialize()
        self.assertEqual((await self.db.get_interruption(tid))["retry_task_id"], new_tid)

    async def test_terminal_or_missing_task_cannot_be_interrupted(self):
        tid = await self._create_in_state("COMPLETED")
        self.assertFalse(await self.db.interrupt_task(tid, "server_restart"))
        from server.storage.database import TaskNotFoundError
        with self.assertRaises(TaskNotFoundError):
            await self.db.interrupt_task("missing", "server_restart")
        with self.assertRaises(ValueError):
            await self.db.interrupt_task(tid, "")

    async def test_automatic_replay_does_not_occur(self):
        tid = await self._create_in_state("WAITING_ACK", command="upload")
        self.assertTrue(await self.db.interrupt_task(tid, "connection_lost"))
        server = C2Server(self.db)
        self.assertEqual(len(await self.db.list_tasks()), 1)
        with self.assertRaisesRegex(ValueError, "only read-only"):
            await server.retry_interrupted_readonly(tid)
        self.assertEqual(len(await self.db.list_tasks()), 1)
        self.assertIsNone((await self.db.get_interruption(tid))["retry_task_id"])


class TestExpandedActualTLS(TestRealTLSTransfers):
    """Inherit existing real-TLS fixture; audit additional running behaviors."""

    async def test_tls_ping_pong_and_heartbeat(self):
        self.assertTrue(await self.app.ping_agent(self.agent_id))
        self.assertEqual(self.app.pending_pings, {})
        # The agent sends periodic BEACON on the *real* TLS connection.
        with mock.patch.object(self.db, "touch_agent", wraps=self.db.touch_agent) as touched:
            await self.wait_for(lambda: touched.await_count >= 1, timeout=2.5)
        self.assertTrue(await self.app.ping_agent(self.agent_id))

    async def test_tls_readonly_tasks_and_rejected_shell(self):
        for cmd, params in (
            ("echo", {"text": "bonjour"}),
            ("get_info", {}),
            ("shell", {"command": "pwd"}),
            ("shell", {"command": "whoami"}),
            ("shell", {"command": "uname"}),
        ):
            with self.subTest(cmd=cmd, params=params):
                tid = await self.app.dispatch_task(self.agent_id, cmd, params)
                self.assertEqual(await self.wait_completed(tid), "COMPLETED")
                self.assertEqual(len(await self.db.list_results(tid)), 1)
        tid = await self.app.dispatch_task(self.agent_id, "shell", {"command": "whoami; id"})
        self.assertEqual(await self.wait_completed(tid), "FAILED")
        self.assertTrue(await self.app.ping_agent(self.agent_id))

    async def test_recovery_manual_readonly_retry_over_tls(self):
        old = str(uuid.uuid4())
        await self.db.create_task(old, self.agent_id, "get_info", {}, "PENDING")
        await self.db.update_task_status(old, "WAITING_ACK")
        self.assertTrue(await self.db.interrupt_task(old, "connection_lost"))
        self.assertEqual(len(await self.db.list_tasks()), 1)
        new = await self.app.retry_interrupted_readonly(old)
        self.assertNotEqual(new, old)
        self.assertEqual(await self.wait_completed(new), "COMPLETED")
        self.assertEqual((await self.db.get_task(old))["status"], "CANCELLED")
        self.assertEqual((await self.db.get_interruption(old))["retry_task_id"], new)
        with self.assertRaisesRegex(ValueError, "already retried"):
            await self.app.retry_interrupted_readonly(old)

    async def test_concurrent_readonly_retries_do_not_duplicate_dispatch(self):
        old = str(uuid.uuid4())
        await self.db.create_task(old, self.agent_id, "echo", {"text": "one"}, "PENDING")
        self.assertTrue(await self.db.interrupt_task(old, "server_restart"))
        attempts = await asyncio.gather(
            self.app.retry_interrupted_readonly(old),
            self.app.retry_interrupted_readonly(old),
            return_exceptions=True,
        )
        successes = [x for x in attempts if isinstance(x, str)]
        refusals = [x for x in attempts if isinstance(x, ValueError)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(refusals), 1)
        self.assertEqual(await self.wait_completed(successes[0]), "COMPLETED")
        self.assertEqual(len(await self.db.list_tasks()), 2)
        self.assertEqual((await self.db.get_interruption(old))["retry_task_id"], successes[0])

    async def test_cli_ping_and_self_remove_are_real_agent_operations(self):
        import io
        from rich.console import Console
        buf = io.StringIO()
        self.app._test_console = Console(file=buf, highlight=False,
                                         no_color=True, width=200)
        inputs = iter([f"ping {self.agent_id[:8]}",
                       f"task {self.agent_id[:8]} self_remove", "quit"])
        async def fake_input(*args, **kwargs):
            return next(inputs)
        with mock.patch("server.main.asyncio.to_thread", side_effect=fake_input):
            await self.app.cli()
        output = buf.getvalue()
        self.assertIn("PONG", output)
        self.assertIn("Task dispatched", output)
        task = next(t for t in await self.db.list_tasks() if t["command"] == "self_remove")
        self.assertEqual(await self.wait_completed(task["task_id"]), "COMPLETED")
        await asyncio.wait_for(self.agent_task, 4)

    async def test_limited_self_remove_stops_reconnect_and_preserves_user_files(self):
        (self.agent_files / "user-sample.txt").write_text("keep this content", encoding="utf-8")
        await self.wait_for(lambda: bool(list(self.agent_files.glob("runtime-state-*.json"))))
        tid = await self.app.dispatch_task(self.agent_id, "self_remove", {})
        self.assertEqual(await self.wait_completed(tid), "COMPLETED")
        results = await self.db.list_results(tid)
        # The test agent runs from the project source tree (not a pa-agent-lab-*
        # installed copy), so the uninstall step is skipped.  Both the old and
        # new message formats indicate that installed files were not deleted.
        output = results[0]["output"]
        self.assertTrue(
            "NOT deleted" in output or "were NOT deleted" in output,
            f"self_remove output should confirm files were not deleted: {output!r}",
        )
        await asyncio.wait_for(self.agent_task, 4)
        self.assertFalse(list(self.agent_files.glob("runtime-state-*.json")))
        self.assertEqual((self.agent_files / "user-sample.txt").read_text(), "keep this content")
        await self.wait_for(lambda: self.agent_id not in self.app.connections)
        # No reconnection after a deliberately completed decommission.
        await asyncio.sleep(0.3)
        self.assertNotIn(self.agent_id, self.app.connections)
        self.assertEqual((await self.db.get_task(tid))["status"], "COMPLETED")

    async def test_rejected_self_remove_parameters_does_not_stop_agent(self):
        tid = await self.app.dispatch_task(self.agent_id, "self_remove", {"force": True})
        self.assertEqual(await self.wait_completed(tid), "FAILED")
        self.assertTrue(await self.app.ping_agent(self.agent_id))


class TestSelfRemoveCommand(unittest.TestCase):
    def test_rejects_unsafe_parameters(self):
        for params in ({"paths": ["/tmp"]}, {"erase": True}, {"force": True}):
            with self.assertRaises(ValueError):
                execute_allowed("self_remove", params)

    def test_describes_its_limits(self):
        message = execute_allowed("self_remove", {})
        self.assertIn("NOT deleted", message)

class TestTLSCertificateBoundary(TestRealTLSTransfers):
    async def test_untrusted_ca_refused_by_real_tls_listener(self):
        import ssl
        import subprocess
        import tempfile
        # Generate a distinct authority; the agent must not trust it.
        with tempfile.TemporaryDirectory() as td:
            wrong_cert = Path(td) / "wrong.crt"
            wrong_key = Path(td) / "wrong.key"
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-nodes", "-days", "1", "-keyout", str(wrong_key),
                "-out", str(wrong_cert), "-subj", "/CN=wrong-ca",
            ], capture_output=True, check=True, timeout=15)
            client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(wrong_cert))
            with self.assertRaises(ssl.SSLCertVerificationError):
                await asyncio.open_connection("127.0.0.1", self.port,
                                              ssl=client, server_hostname="127.0.0.1")
        self.assertTrue(await self.app.ping_agent(self.agent_id))
