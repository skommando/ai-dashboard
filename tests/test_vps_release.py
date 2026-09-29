"""Exercise the release gates and SQLite backup without touching systemd."""

import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vps = load("vps_release", ROOT / "deploy/vps/release.py")
local = load("local_release", ROOT / "scripts/release.py")


class SourceTests(unittest.TestCase):
    def test_cross_auth_deploy_requires_old_credentials_before_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = vps.Release(Path(directory) / "app")
            old = manager.releases / ("a" * 40)
            old.mkdir(parents=True)
            fake_current = mock.Mock()
            fake_current.is_symlink.return_value = True
            fake_current.resolve.return_value = old
            with mock.patch.object(manager, "preflight", return_value=(0, 0, {
                    "DASHBOARD_LOGIN_USERNAME": "viewer", "DASHBOARD_LOGIN_PASSWORD": "new-pass",
                    "DASHBOARD_SESSION_SECRET": "s" * 64})), \
                 mock.patch.object(manager, "current", fake_current), \
                 mock.patch.object(manager, "layout") as layout:
                with self.assertRaisesRegex(ValueError, "旧版凭据"):
                    manager.deploy("https://github.com/example/dashboard.git", "b" * 40,
                                   Path("/usr/bin/python3.12"), Path("/etc/nginx/site.conf"),
                                   Path("/etc/nginx/dashboard.inc"), Path("/var/www/dashboard"),
                                   Path("/usr/sbin/nginx"))
                layout.assert_not_called()

    def test_manual_rollback_rejects_pre_session_release_before_backup_or_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = vps.Release(Path(directory) / "app")
            target = manager.releases / ("a" * 40)
            target.mkdir(parents=True)
            with mock.patch.object(manager, "validate_release", return_value=target), \
                 mock.patch.object(manager, "backup") as backup, \
                 mock.patch.object(manager, "switch") as switch:
                with self.assertRaisesRegex(ValueError, "旧版认证协议"):
                    manager._rollback_locked("a" * 40)
                backup.assert_not_called()
                switch.assert_not_called()

    def test_rollback_refuses_dirty_target_before_backup_or_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = vps.Release(Path(directory) / "app")
            sha = "a" * 40
            target = manager.releases / sha
            (target / ".venv/bin").mkdir(parents=True)
            (target / ".venv/bin/python").write_text("")
            def fake_run(*args, **kwargs):
                return " M dashboard/server.py" if "status" in args else sha
            with mock.patch.object(vps, "run", side_effect=fake_run), \
                 mock.patch.object(vps, "read_environment", return_value={}), \
                 mock.patch.object(manager, "current"), \
                 mock.patch.object(manager, "backup") as backup, \
                 mock.patch.object(manager, "switch") as switch:
                with self.assertRaisesRegex(ValueError, "存在改动"):
                    manager._rollback_locked(sha)
                backup.assert_not_called()
                switch.assert_not_called()

    def test_tls_server_does_not_require_basic_auth(self):
        header = "server {\n listen 443 ssl;\n auth_basic_user_file /private/htpasswd;\n"
        self.assertFalse(vps.server_has_tls_without_basic(header + ' auth_basic "viewer";\n location / { }\n}\n'))
        self.assertTrue(vps.server_has_tls_without_basic(header + " auth_basic off;\n}\n"))
        self.assertTrue(vps.server_has_tls_without_basic(header + "}\n"))

    def test_paths_reject_control_characters_and_nonabsolute_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(Path(directory).anchor) / "dashboard-path-tests"
            self.assertEqual(vps.validate_path(root / "app"), root / "app")
            for path in (Path("relative/path"), root / "bad\npath", root / "space path",
                         root / "bad;include", root / "bad#comment", root / "bad{brace}", root / ".."):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    vps.validate_path(path, no_space=True)

    @unittest.skipUnless(os.name == "nt", "PowerShell start path guard")
    def test_windows_start_rejects_runtime_equal_to_repository(self):
        result = subprocess.run(["powershell", "-NoProfile", "-File", str(ROOT / "tools/start.ps1"),
                                 "-Runtime", str(ROOT)], capture_output=True, text=True, errors="replace")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[runtime_in_repo]", result.stdout + result.stderr)

    def test_only_public_github_https_source_is_accepted(self):
        good = "https://github.com/example/dashboard.git"
        self.assertEqual(good, vps.validate_repo_url(good))
        for bad in ("http://github.com/example/dashboard", "https://user:secret@github.com/example/dashboard",
                    "https://git.example.invalid/example/dashboard", "https://github.com/example/dashboard?token=x"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                vps.validate_repo_url(bad)

    def test_fetch_refuses_unreviewed_main_before_creating_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = vps.Release(Path(directory) / "app")
            seen = []

            def fake_run(*args, **kwargs):
                seen.append(args)
                if args[:2] == ("git", "ls-remote"):
                    return "a" * 40 + "\trefs/heads/main"
                raise AssertionError("unexpected mutation")

            with mock.patch.object(vps, "run", fake_run):
                with self.assertRaises(ValueError):
                    manager.fetch_main("https://github.com/example/dashboard.git", "b" * 40)
            self.assertEqual(len(seen), 1)
            self.assertFalse(manager.repo.exists())

    def test_reused_release_refuses_dirty_source_before_venv_work(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = vps.Release(Path(directory) / "app")
            sha = "a" * 40
            (manager.releases / sha).mkdir(parents=True)

            def fake_run(*args, **kwargs):
                if "rev-parse" in args:
                    return sha
                if "status" in args:
                    return " M dashboard/server.py"
                raise AssertionError("venv preparation must not start")

            with mock.patch.object(vps, "run", side_effect=fake_run):
                with self.assertRaisesRegex(ValueError, "存在改动"):
                    manager.stage(sha, Path(directory) / "python")


class BackupTests(unittest.TestCase):
    def test_layout_makes_only_data_directory_service_writable(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = vps.Release(Path(directory) / "app")
            manager.database.parent.mkdir(parents=True)
            manager.database.write_bytes(b"database")
            manager.environment_file.write_text("private")
            with mock.patch.object(vps.os, "chown", create=True) as chown, \
                 mock.patch.object(vps.os, "chmod") as chmod:
                manager.layout(998, 997)
            self.assertIn(mock.call(manager.shared / "data", 998, 997), chown.call_args_list)
            self.assertIn(mock.call(manager.shared / "data", 0o700), chmod.call_args_list)
            self.assertIn(mock.call(manager.shared, 0o750), chmod.call_args_list)
            self.assertIn(mock.call(manager.environment_file, 0, 997), chown.call_args_list)

    def test_backup_includes_committed_wal_content_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "live.sqlite3"
            target = Path(directory) / "backup.sqlite3"
            with closing(sqlite3.connect(source)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE receipts (key TEXT PRIMARY KEY)")
                db.execute("INSERT INTO receipts VALUES ('persisted')")
                db.commit()
                vps.backup_database(source, target)
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute("SELECT key FROM receipts").fetchone()[0], "persisted")
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            with closing(sqlite3.connect(source)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)

    def test_environment_parser_rejects_duplicate_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.env"
            valid = ("DASHBOARD_DB_PATH=/opt/ai-dashboard/shared/data/dashboard.sqlite3\n"
                     "DASHBOARD_WEB_DIR=/opt/ai-dashboard/current/web\n"
                     "DASHBOARD_LOGIN_USERNAME=viewer\n"
                     "DASHBOARD_LOGIN_PASSWORD='with spaces # and = signs'\n"
                     "DASHBOARD_SESSION_SECRET=" + "s" * 64 + "\n")
            path.write_text(valid, encoding="utf-8")
            self.assertEqual(vps.read_environment(path)["DASHBOARD_LOGIN_PASSWORD"],
                             "with spaces # and = signs")
            path.write_text(valid + "DASHBOARD_VIEW_USERNAME=old\nDASHBOARD_VIEW_PASSWORD=old-secret\n",
                            encoding="utf-8")
            self.assertEqual(vps.read_environment(path)["DASHBOARD_VIEW_USERNAME"], "old")
            for content in (valid + "DASHBOARD_LOGIN_USERNAME=again\n", valid + "EXTRA=value\n",
                            valid.replace("s" * 64, "short")):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    vps.read_environment(path)


@unittest.skipIf(os.name == "nt", "Linux symlink and flock behavior")
class RecoveryTests(unittest.TestCase):
    def test_failed_deploy_restores_site_unit_and_previous_release(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            manager = vps.Release(base / "app", unit=base / "ai-dashboard.service")
            manager.root.mkdir()
            old = manager.root / "releases" / ("a" * 40)
            new = manager.root / "releases" / ("b" * 40)
            old.mkdir(parents=True)
            new.mkdir()
            manager.current.symlink_to(old)
            site, include = base / "site.conf", base / "dashboard.inc"
            site.write_text("old site", encoding="utf-8")
            include.write_text("old include", encoding="utf-8")
            manager.unit.write_text("old unit", encoding="utf-8")
            backup = base / "backup"
            backup.mkdir()
            env = {"DASHBOARD_LOGIN_USERNAME": "viewer", "DASHBOARD_LOGIN_PASSWORD": "secret",
                   "DASHBOARD_SESSION_SECRET": "s" * 64,
                   "DASHBOARD_VIEW_USERNAME": "old-viewer", "DASHBOARD_VIEW_PASSWORD": "old-secret"}

            def switch(release, environment):
                vps.atomic_symlink(manager.current, release)
                return old

            nginx_checks = 0
            def command(*args, **kwargs):
                nonlocal nginx_checks
                if args == ("/usr/sbin/nginx", "-t"):
                    nginx_checks += 1
                    if nginx_checks == 1:
                        raise RuntimeError("nginx test failed")
                return ""

            with mock.patch.object(manager, "preflight", return_value=(0, 0, env)), \
                 mock.patch.object(manager, "layout"), \
                 mock.patch.object(manager, "fetch_main"), \
                 mock.patch.object(manager, "stage", return_value=new), \
                 mock.patch.object(manager, "backup", return_value=backup), \
                 mock.patch.object(manager, "install_unit", side_effect=lambda: manager.unit.write_text("new unit")), \
                 mock.patch.object(manager, "configure_site", side_effect=lambda *a: (site.write_text("new site"), include.write_text("new include"))), \
                 mock.patch.object(manager, "switch", side_effect=switch), \
                 mock.patch.object(vps, "run", side_effect=command), \
                 mock.patch.object(vps.subprocess, "run", return_value=mock.Mock(returncode=0)):
                with self.assertRaisesRegex(RuntimeError, "nginx test failed"):
                    manager.deploy("https://github.com/example/dashboard.git", "b" * 40,
                                   base / "python", site, include, base, Path("/usr/sbin/nginx"))
            self.assertEqual(manager.current.resolve(), old)
            self.assertEqual(site.read_text(), "old site")
            self.assertEqual(include.read_text(), "old include")
            self.assertEqual(manager.unit.read_text(), "old unit")

    def test_failed_code_rollback_keeps_current_and_database(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            manager = vps.Release(base / "app")
            manager.releases.mkdir(parents=True)
            old, current = manager.releases / ("a" * 40), manager.releases / ("b" * 40)
            (old / ".venv/bin").mkdir(parents=True)
            (old / ".venv/bin/python").write_text("")
            (old / "dashboard").mkdir()
            (old / "dashboard/session.py").write_text("", encoding="utf-8")
            current.mkdir()
            manager.current.symlink_to(current)
            manager.shared.mkdir()
            manager.environment_file.write_text(
                "DASHBOARD_DB_PATH=/opt/ai-dashboard/shared/data/dashboard.sqlite3\n"
                "DASHBOARD_WEB_DIR=/opt/ai-dashboard/current/web\n"
                "DASHBOARD_LOGIN_USERNAME=viewer\nDASHBOARD_LOGIN_PASSWORD=secret\n"
                "DASHBOARD_SESSION_SECRET=" + "s" * 64 + "\n")
            manager.database.parent.mkdir()
            manager.database.write_bytes(b"unchanged")

            def switch(release, environment):
                vps.atomic_symlink(manager.current, release)
                raise RuntimeError("health failed")

            with mock.patch.object(manager, "backup", return_value=base / "backup"), \
                 mock.patch.object(manager, "switch", side_effect=switch), \
                 mock.patch.object(manager, "validate_release", return_value=old), \
                 mock.patch.object(vps, "run", side_effect=lambda *a, **k: "a" * 40 if a[:2] == ("git", "-C") else ""):
                with self.assertRaisesRegex(RuntimeError, "health failed"):
                    manager._rollback_locked("a" * 40)
            self.assertEqual(manager.current.resolve(), current)
            self.assertEqual(manager.database.read_bytes(), b"unchanged")


class LocalGateTests(unittest.TestCase):
    def test_default_record_is_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertEqual(local.default_record("e" * 40).parent,
                             Path(directory) / "ai-dashboard" / "release-checks")

    def test_skip_requires_reason_and_records_it(self):
        sha = "c" * 40
        with self.assertRaises(ValueError):
            local.check(sha, skip_tests=True)
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "gate.json"
            with mock.patch.object(local.subprocess, "check_output", side_effect=[sha, "", ""]), \
                 mock.patch.object(local, "command") as command:
                local.check(sha, skip_tests=True, reason="用户要求暂缓测试", record=record)
            command.assert_called_once_with(["node", "scripts/build-demo.cjs"])
            self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["skip_reason"], "用户要求暂缓测试")

    def test_default_gate_runs_both_test_suites(self):
        sha = "d" * 40
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(local.subprocess, "check_output", side_effect=[sha, "", ""]), \
                 mock.patch.object(local, "command") as command:
                local.check(sha, record=Path(directory) / "gate.json")
            self.assertEqual(command.call_count, 3)
            self.assertEqual(command.call_args_list[1].args[0][:2], ["node", "--test"])
            self.assertIn("unittest", command.call_args_list[2].args[0])


if __name__ == "__main__":
    unittest.main()
