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
import uuid


SERVICE = Path(__file__).resolve().parents[1] / "scripts" / "service.py"
START_SCRIPT = SERVICE.with_name("start-dashboard.ps1")
STOP_SCRIPT = SERVICE.with_name("stop-dashboard.ps1")
ROOT_VENV_PYTHON = Path(os.environ.get(
    "DASHBOARD_TEST_VENV_PYTHON", str(SERVICE.parent.parent / ".venv" / "Scripts" / "python.exe")
))


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


@unittest.skipUnless(os.name == "nt", "Windows Job Object supervisor; Linux uses systemd")
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

    def call(self, action, instance_id=None):
        command = [sys.executable, str(SERVICE), action, "--config", str(self.config)]
        if instance_id is not None:
            command.extend(["--instance-id", instance_id])
        return subprocess.run(
            command,
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

    def test_stop_requires_matching_instance_id_when_supplied(self):
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", "import time; time.sleep(60)"]}])
        self.launch()
        state = self.wait_status(lambda s: s.get("components", [{}])[0].get("pid"))
        wrong = self.call("stop", instance_id=uuid.uuid4().hex)
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn("instance", wrong.stderr.lower())
        self.assertEqual(self.call("stop", instance_id=state["instance_id"]).returncode, 0)

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

    def test_stable_heartbeat_is_written_about_once_per_second(self):
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", "import time; time.sleep(60)"]}])
        self.launch()
        self.wait_status(lambda s: s.get("components", [{}])[0].get("pid"))
        state_file = self.runtime / "service-state.json"
        previous = state_file.stat().st_mtime_ns
        writes = 0
        deadline = time.monotonic() + 2.2
        while time.monotonic() < deadline:
            current = state_file.stat().st_mtime_ns
            if current != previous:
                writes += 1
                previous = current
            time.sleep(0.05)
        self.assertGreaterEqual(writes, 1)
        self.assertLessEqual(writes, 3, "stable state should not fsync on every 0.1-second poll")

    def test_child_launcher_does_not_start_component_without_release(self):
        marker = self.runtime / "started.txt"
        code = f"from pathlib import Path; Path({str(marker)!r}).write_text('started')"
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", code]}])
        launcher = subprocess.Popen(
            [sys.executable, str(SERVICE), "_child"], cwd=self.root,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        def clean_launcher():
            if launcher.poll() is None:
                launcher.kill()
                launcher.wait(timeout=5)
            for stream in (launcher.stdin, launcher.stdout, launcher.stderr):
                stream.close()
        self.addCleanup(clean_launcher)
        time.sleep(0.25)
        self.assertIsNone(launcher.poll(), "launcher must wait for a supervisor release")
        self.assertFalse(marker.exists())
        launcher.stdin.close()
        launcher.wait(timeout=5)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "nt", "nested Job Object lifecycle is Windows-only")
    def test_component_launcher_exit_cleans_descendants_before_restart(self):
        child_pid_file = self.runtime / "grandchild.pid"
        code = (
            "import subprocess,sys; "
            f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            f"open({str(child_pid_file)!r},'w').write(str(p.pid)); "
            "raise SystemExit(7)"
        )
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", code]}])
        self.launch()
        self.wait_status(lambda s: s.get("components", [{}])[0].get("restarts", 0) >= 1)
        grandchild_pid = int(child_pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 2
        while process_exists(grandchild_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(process_exists(grandchild_pid), "old component tree survived launcher exit")

    @unittest.skipUnless(os.name == "nt", "PowerShell launcher is Windows-only")
    def test_powershell_launcher_handles_python_path_with_spaces(self):
        self.write_config([{"name": "reader", "command": [sys.executable, "-c", "import time; time.sleep(60)"]}])
        system_python = str(Path(sys.base_prefix) / "python.exe")
        pythonw = str(Path(sys.base_prefix) / "pythonw.exe")
        instance_id = uuid.uuid4().hex
        self.assertTrue(Path(pythonw).exists())
        self.addCleanup(lambda: self.call("stop", instance_id=instance_id))
        started = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(START_SCRIPT),
             "-Config", str(self.config), "-Python", system_python, "-Pythonw", pythonw,
             "-InstanceId", instance_id],
            cwd=self.root, capture_output=True, text=True, timeout=8,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.wait_status(lambda s: s.get("instance_id") == instance_id and s.get("components", [{}])[0].get("pid"))
        stopped = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(STOP_SCRIPT),
             "-Config", str(self.config), "-Python", system_python],
            cwd=self.root, capture_output=True, text=True, timeout=8,
        )
        self.assertEqual(stopped.returncode, 0, stopped.stderr)

    @unittest.skipUnless(os.name == "nt" and ROOT_VENV_PYTHON.exists(), "redirecting venv pythonw unavailable")
    def test_powershell_launcher_handles_redirecting_venv_pythonw(self):
        self.write_config([{"name": "reader", "command": [str(ROOT_VENV_PYTHON), "-c", "import time; time.sleep(60)"]}])
        instance_id = uuid.uuid4().hex
        self.addCleanup(lambda: self.call("stop", instance_id=instance_id))
        started = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(START_SCRIPT),
             "-Config", str(self.config), "-Python", str(ROOT_VENV_PYTHON),
             "-Pythonw", str(ROOT_VENV_PYTHON.with_name("pythonw.exe")),
             "-InstanceId", instance_id],
            cwd=self.root, capture_output=True, text=True, timeout=13,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        state = self.wait_status(lambda s: s.get("instance_id") == instance_id and s.get("components", [{}])[0].get("pid"))
        self.assertTrue(state["running"])

    @unittest.skipUnless(os.name == "nt", "PowerShell launcher is Windows-only")
    def test_powershell_launcher_reports_component_start_failure(self):
        self.write_config([{"name": "reader", "command": [str(self.root / "missing.exe")]}])
        pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
        instance_id = uuid.uuid4().hex
        self.addCleanup(lambda: self.call("stop", instance_id=instance_id))
        started = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(START_SCRIPT),
             "-Config", str(self.config), "-Python", sys.executable, "-Pythonw", pythonw,
             "-InstanceId", instance_id],
            cwd=self.root, capture_output=True, text=True, timeout=16,
        )
        if started.returncode == 0:
            self.wait_status(lambda s: s.get("running"))
        self.assertNotEqual(started.returncode, 0)
        self.assertIn("launch_failed", started.stdout + started.stderr)
        self.assertNotIn("top-secret-password", started.stdout + started.stderr)

    @unittest.skipUnless(os.name == "nt", "PowerShell launcher is Windows-only")
    def test_powershell_launcher_reports_invalid_config(self):
        self.write_config([{"name": "reader", "command": []}])
        pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
        instance_id = uuid.uuid4().hex
        self.addCleanup(lambda: self.call("stop", instance_id=instance_id))
        started = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(START_SCRIPT),
             "-Config", str(self.config), "-Python", sys.executable, "-Pythonw", pythonw,
             "-InstanceId", instance_id],
            cwd=self.root, capture_output=True, text=True, timeout=8,
        )
        self.assertNotEqual(started.returncode, 0)
        self.assertFalse((self.runtime / "service-state.json").exists())
        self.assertNotIn("top-secret-password", started.stdout + started.stderr)


if __name__ == "__main__":
    unittest.main()
