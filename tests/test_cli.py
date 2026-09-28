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
            result = send_request(self.request, "secret", "http://127.0.0.1:8811", retries=2)
        self.assertEqual(result["revision"], 8)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertIn(b'"expected_revision":7', calls[0][1])
        self.assertEqual(calls[0][2]["Idempotency-key"], "fixed-key")

    def test_conflict_never_retries_or_edits_request_file(self):
        from clients.report_progress import prepare_request, send_request, ReportError
        from io import BytesIO
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        original = self.request.read_bytes()
        calls = []

        def conflict(request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 409, "conflict", {},
                            BytesIO(b'{"error":{"code":"revision_conflict"},"current_revision":9}'))

        with patch("clients.report_progress.urlopen", side_effect=conflict), \
             patch("clients.report_progress.time.sleep") as sleep:
            with self.assertRaises(ReportError) as error:
                send_request(self.request, "secret", "http://127.0.0.1:8811", retries=4)
        self.assertIn("9", str(error.exception))
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()
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
                    send_request(self.request, "secret", retries=4)
                self.assertEqual(len(calls), 1)
                sleep.assert_not_called()

    def test_token_is_never_sent_to_non_loopback_url(self):
        from clients.report_progress import prepare_request, send_request, ReportError
        prepare_request("one", self.snapshot, self.request, "fixed-key")
        with patch("clients.report_progress.urlopen") as open_url:
            with self.assertRaises(ReportError):
                send_request(self.request, "secret", "https://unrelated.example")
            open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
