import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "dashboard.sqlite3"

    def test_register_requires_file_only_stores_hash_and_rotation_revokes_old_token(self):
        from dashboard.manage import main
        from dashboard.store import authorized_revision
        first = Path(self.temp.name) / "first.token"
        second = Path(self.temp.name) / "second.token"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["init", "--db", str(self.db)]), 0)
            self.assertEqual(main(["register", "one", "--db", str(self.db), "--token-file", str(first)]), 0)
        token = first.read_text(encoding="utf-8").strip()
        self.assertTrue(token)
        self.assertNotIn(token, output.getvalue())
        db = sqlite3.connect(self.db)
        try:
            stored = db.execute("SELECT token_hash FROM projects WHERE project_id='one'").fetchone()[0]
            self.assertNotEqual(stored, token)
        finally:
            db.close()
        self.assertEqual(authorized_revision(str(self.db), "one", token), 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertNotEqual(main(["register", "one", "--db", str(self.db), "--token-file", str(second)]), 0)
        self.assertFalse(second.exists())
        self.assertEqual(authorized_revision(str(self.db), "one", token), 0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["rotate", "one", "--db", str(self.db), "--token-file", str(second)]), 0)
        self.assertIsNone(authorized_revision(str(self.db), "one", token))
        self.assertEqual(authorized_revision(str(self.db), "one", second.read_text(encoding="utf-8").strip()), 0)


class ReporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.snapshot = Path(self.temp.name) / "snapshot.json"
        self.request = Path(self.temp.name) / "request.json"
        self.snapshot.write_text('{"schema_version":1,"expected_revision":7,"project":{"name":"示例"}}', encoding="utf-8")

    def test_prepare_persists_body_and_key_then_retry_uses_identical_request(self):
        from clients.report_progress import prepare_request, send_request
        from io import BytesIO
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        self.snapshot.write_text("{}", encoding="utf-8")
        calls = []

        def fake_open(request, timeout):
            calls.append((request.full_url, request.data, dict(request.headers)))
            if len(calls) == 1:
                raise URLError("offline")
            return BytesIO(b'{"project_id":"one","revision":8,"received_at":"now","replayed":false}')

        with patch("clients.report_progress.urlopen", side_effect=fake_open), \
             patch("clients.report_progress.time.sleep"):
            result = send_request(self.request, "secret", "http://127.0.0.1:8810", retries=2)
        self.assertEqual(result["revision"], 8)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertIn(b'"expected_revision":7', calls[0][1])
        self.assertEqual(calls[0][2]["Idempotency-key"], "fixed-key")
        self.assertEqual(calls[0][2]["X-project-token"], "secret")
        self.assertNotIn("Authorization", calls[0][2])

    def test_conflict_never_retries_or_edits_request_file(self):
        from clients.report_progress import prepare_request, send_request, ReportError
        from io import BytesIO
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        original = self.request.read_bytes()
        calls = []
        error_body = BytesIO(b'{"error":{"code":"revision_conflict"},"current_revision":9}')

        def conflict(request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 409, "conflict", {},
                            error_body)

        with patch("clients.report_progress.urlopen", side_effect=conflict), \
             patch("clients.report_progress.time.sleep") as sleep:
            with self.assertRaises(ReportError) as error:
                send_request(self.request, "secret", "http://127.0.0.1:8810", retries=4)
        self.assertIn("9", str(error.exception))
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()
        self.assertTrue(error_body.closed)
        self.assertEqual(self.request.read_bytes(), original)

    def test_auth_and_validation_errors_never_retry(self):
        from clients.report_progress import prepare_request, send_request, ReportError
        from io import BytesIO
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        for status in (401, 422):
            calls = []

            def rejected(request, timeout):
                calls.append(request)
                raise HTTPError(request.full_url, status, "rejected", {}, BytesIO(b"{}"))

            with self.subTest(status=status), patch("clients.report_progress.urlopen", side_effect=rejected), \
                 patch("clients.report_progress.time.sleep") as sleep:
                with self.assertRaises(ReportError):
                    send_request(self.request, "secret", "http://127.0.0.1:8810", retries=4)
                self.assertEqual(len(calls), 1)
                sleep.assert_not_called()

    def test_token_is_never_sent_to_insecure_external_url(self):
        from clients.report_progress import prepare_request, send_request, ReportError
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        with patch("clients.report_progress.urlopen") as open_url:
            with self.assertRaises(ReportError):
                send_request(self.request, "secret", "http://unrelated.example:8810")
            open_url.assert_not_called()

    def test_https_and_revision_send_only_project_token(self):
        from clients.report_progress import fetch_revision
        from io import BytesIO
        calls = []
        def fake_open(request, timeout):
            calls.append(request)
            return BytesIO(b'{"project_id":"one","revision":7}')
        with patch("clients.report_progress.urlopen", side_effect=fake_open):
            result = fetch_revision("one", "secret", "https://view.example")
        self.assertEqual(result["revision"], 7)
        self.assertEqual(calls[0].full_url, "https://view.example/api/v1/projects/one/revision")
        self.assertEqual(calls[0].headers["X-project-token"], "secret")
        self.assertNotIn("Authorization", calls[0].headers)

    def test_url_validation_and_retries_happen_before_network(self):
        from clients.report_progress import prepare_request, send_request, ReportError
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        invalid = ("http://view.example:8810", "http://127.0.0.1", "https://user:pass@view.example",
                   "https://view.example/path", "https://view.example?x=1", "https://view.example:0",
                   "https://view.example\r\n")
        with patch("clients.report_progress.urlopen") as open_url:
            for url in invalid:
                with self.subTest(url=url), self.assertRaises(ReportError):
                    send_request(self.request, "secret", url)
            for retries in (-1, 11):
                with self.assertRaises(ReportError):
                    send_request(self.request, "secret", "https://view.example", retries)
            open_url.assert_not_called()

    def test_main_requires_explicit_base_url_and_rejects_removed_basic_option(self):
        from clients.report_progress import main, prepare_request
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        token = Path(self.temp.name) / "token"
        token.write_text("secret", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["send", "--request-file", str(self.request), "--token-file", str(token)])
            with self.assertRaises(SystemExit):
                main(["send", "--request-file", str(self.request), "--token-file", str(token),
                      "--basic-auth-file", "removed", "--base-url", "https://view.example"])

    def test_redirect_is_not_followed_and_error_omits_credentials(self):
        from clients.report_progress import prepare_request, send_request, ReportError
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        visited = []
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_PUT(self):
                visited.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/landing")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(ReportError) as error:
                send_request(self.request, "secret", f"http://127.0.0.1:{server.server_port}")
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(visited, ["/api/v1/projects/one/snapshot"])
        self.assertNotIn("secret", str(error.exception))

    def test_cli_reads_token_file_and_sends_without_printing_secrets(self):
        from clients.report_progress import main, prepare_request
        from io import BytesIO
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        token = Path(self.temp.name) / "token"
        token.write_text("secret", encoding="utf-8")
        seen = []
        def fake_open(request, timeout):
            seen.append(request)
            return BytesIO(b'{"project_id":"one","revision":8,"received_at":"now","replayed":false}')
        output = io.StringIO()
        with patch("clients.report_progress.urlopen", side_effect=fake_open), contextlib.redirect_stdout(output):
            status = main(["send", "--request-file", str(self.request), "--token-file", str(token),
                           "--base-url", "https://view.example"])
        self.assertEqual(status, 0)
        self.assertEqual(seen[0].headers["X-project-token"], "secret")
        self.assertNotIn("secret", output.getvalue())
        self.assertIn("revision=8", output.getvalue())

    def test_cli_revision_reads_token_environment(self):
        from clients.report_progress import main
        from io import BytesIO
        seen = []
        def fake_open(request, timeout):
            seen.append(request)
            return BytesIO(b'{"project_id":"one","revision":7}')
        env = {"REPORT_TOKEN": "secret"}
        output = io.StringIO()
        with patch.dict(os.environ, env), patch("clients.report_progress.urlopen", side_effect=fake_open), \
             contextlib.redirect_stdout(output):
            status = main(["revision", "one", "--token-env", "REPORT_TOKEN", "--base-url", "https://view.example"])
        self.assertEqual(status, 0)
        self.assertEqual(seen[0].headers["X-project-token"], "secret")
        self.assertEqual(output.getvalue().strip(), "revision=7")


class ServerEntryTests(unittest.TestCase):
    def test_default_is_one_loopback_service_and_old_write_role_rejected(self):
        from dashboard.server import main
        with tempfile.TemporaryDirectory() as temp:
            variables = {"DASHBOARD_DB_PATH": str(Path(temp) / "db.sqlite3"),
                         "DASHBOARD_WEB_DIR": temp, "DASHBOARD_LOGIN_USERNAME": "viewer",
                         "DASHBOARD_LOGIN_PASSWORD": "ComplexPassphrase5!x", "DASHBOARD_SESSION_SECRET": "s" * 64}
            with patch.dict(os.environ, variables), patch("dashboard.server.uvicorn.run") as run:
                self.assertEqual(main([]), 0)
                self.assertEqual(run.call_args.kwargs["host"], "127.0.0.1")
                self.assertEqual(run.call_args.kwargs["port"], 8810)
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    main(["--role", "write"])


if __name__ == "__main__":
    unittest.main()
