"""Lifecycle checks for the local service supervisor."""

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


SERVICE = Path(__file__).resolve().parents[1] / "scripts" / "service.py"
START_SCRIPT = SERVICE.with_name("start-dashboard.ps1")
STOP_SCRIPT = SERVICE.with_name("stop-dashboard.ps1")


def process_exists(pid):
    if os.name != "nt":
        return Path(f"/proc/{pid}").exists()
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x00000102
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / ".runtime"
        self.runtime.mkdir()
        self.config = self.runtime / "service.json"
        self.supervisors = []
        self.addCleanup(self.clean_supervisors)

    def write_config(self, components):
        data = {
            "working_directory": str(self.root),
            "runtime_directory": str(self.runtime),
            "environment": {
                "DASHBOARD_DB_PATH": str(self.runtime / "dashboard.sqlite3"),
                "DASHBOARD_WEB_DIR": str(self.root),
                "DASHBOARD_VIEW_USERNAME": "viewer",
                "DASHBOARD_VIEW_PASSWORD": "top-secret-password",
            },
            "components": components,
        }
        self.config.write_text(json.dumps(data), encoding="utf-8")

    def call(self, action):
        return subprocess.run(
            [sys.executable, str(SERVICE), action, "--config", str(self.config)],
            cwd=self.root, capture_output=True, text=True, timeout=8,
        )

    def launch(self):
        proc = subprocess.Popen(
            [sys.executable, str(SERVICE), "run", "--config", str(self.config)],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.supervisors.append(proc)
        return proc

    def wait_status(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            result = self.call("status")
            last = result
            if result.returncode == 0:
                state = json.loads(result.stdout)
                if predicate(state):
                    return state
            time.sleep(0.1)
        logs = {p.name: p.read_text(encoding="utf-8", errors="replace")[-500:] for p in self.runtime.glob("*.log")}
        processes = [(p.poll(), p.stderr.read().decode(errors="replace") if p.poll() is not None else "") for p in self.supervisors]
        self.fail(f"supervisor did not reach expected status; last={last}; logs={logs}; supervisors={processes}")

    def clean_supervisors(self):
        for proc in self.supervisors:
            if proc.poll() is None:
                try:
                    self.call("stop")
                    proc.wait(timeout=5)
                except Exception:
                    proc.terminate()
                    proc.wait(timeout=5)
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

    def test_invalid_config_rejected_before_runtime_files_are_written(self):
        self.write_config([{"name": "reader", "command": []}])
        result = self.call("run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid configuration", result.stderr)
        self.assertNotIn("top-secret-password", result.stderr)
        self.assertFalse((self.runtime / "service-state.json").exists())

    def test_second_supervisor_refuses_existing_instance(self):
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", "import time; time.sleep(60)"]}])
        self.launch()
        self.wait_status(lambda s: s.get("running") is True)
        duplicate = self.call("run")
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual(len(json.loads(self.call("status").stdout)["components"]), 1)

    def test_crashed_child_restarts_with_delay_and_state_excludes_secrets(self):
        attempts = self.runtime / "attempts.txt"
        code = f"import time; open({str(attempts)!r}, 'a').write(str(time.time()) + '\\n'); raise SystemExit(7)"
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", code]}])
        self.launch()
        state = self.wait_status(lambda s: s.get("components", [{}])[0].get("restarts", 0) >= 2)
        recorded = [float(line) for line in attempts.read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(recorded), 2)
        self.assertGreaterEqual(recorded[1] - recorded[0], 0.4)
        self.assertEqual(state["components"][0]["last_exit_code"], 7)
        self.assertGreater(state["components"][0]["next_restart_at"], state["components"][0]["last_exit_at"])
        serialized = (self.runtime / "service-state.json").read_text(encoding="utf-8")
        self.assertNotIn("top-secret-password", serialized)
        self.assertNotIn("DASHBOARD_VIEW_PASSWORD", serialized)
        self.assertNotIn(str(self.config), serialized)

    def test_stop_only_ends_owned_child_and_ignores_stale_pid(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: unrelated.poll() is None and (unrelated.terminate(), unrelated.wait(timeout=5)))
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", "import time; time.sleep(60)"]}])
        self.runtime.joinpath("service-state.json").write_text(
            json.dumps({"running": True, "instance_id": "stale", "pid": unrelated.pid}), encoding="utf-8"
        )
        stale_stop = self.call("stop")
        self.assertNotEqual(stale_stop.returncode, 0)
        self.assertIsNone(unrelated.poll())
        supervisor = self.launch()
        state = self.wait_status(lambda s: s.get("running") and s.get("components", [{}])[0].get("pid"))
        owned_pid = state["components"][0]["pid"]
        self.assertTrue(process_exists(owned_pid))
        stopped = self.call("stop")
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        supervisor.wait(timeout=5)
        self.assertFalse(process_exists(owned_pid))
        self.assertIsNone(unrelated.poll())

    @unittest.skipUnless(os.name == "nt", "Job Object lifecycle is Windows-only")
    def test_unexpected_supervisor_exit_closes_its_children(self):
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", "import time; time.sleep(60)"]}])
        supervisor = self.launch()
        state = self.wait_status(lambda s: s.get("components", [{}])[0].get("pid"))
        owned_pid = state["components"][0]["pid"]
        self.assertTrue(process_exists(owned_pid))
        supervisor.kill()
        supervisor.wait(timeout=5)
        deadline = time.monotonic() + 3
        while process_exists(owned_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(process_exists(owned_pid), "orphaned child would block the next startup")

    def test_component_log_keeps_bounded_current_and_backup_files(self):
        self.write_config([{
            "name": "reader",
            "command": [sys.executable, "-c", "import os,time; os.write(1,b'x'*2500000); time.sleep(60)"],
        }])
        self.launch()
        self.wait_status(lambda s: s.get("components", [{}])[0].get("pid"))
        current = self.runtime / "reader.log"
        backup = self.runtime / "reader.log.1"
        deadline = time.monotonic() + 5
        while not backup.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(backup.exists())
        self.assertLessEqual(current.stat().st_size, 1_048_576)
        self.assertLessEqual(backup.stat().st_size, 1_048_576)

    @unittest.skipUnless(os.name == "nt", "PowerShell launcher is Windows-only")
    def test_powershell_launcher_handles_python_path_with_spaces(self):
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", "import time; time.sleep(60)"]}])
        pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
        self.assertTrue(Path(pythonw).exists())
        started = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(START_SCRIPT),
             "-Config", str(self.config), "-Python", sys.executable, "-Pythonw", pythonw],
            cwd=self.root, capture_output=True, text=True, timeout=8,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.addCleanup(lambda: self.call("stop"))
        self.wait_status(lambda s: s.get("running") and s.get("components", [{}])[0].get("pid"))
        stopped = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(STOP_SCRIPT),
             "-Config", str(self.config), "-Python", sys.executable],
            cwd=self.root, capture_output=True, text=True, timeout=8,
        )
        self.assertEqual(stopped.returncode, 0, stopped.stderr)


if __name__ == "__main__":
    unittest.main()
