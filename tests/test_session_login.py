"""网页登录与仅项目令牌上报的安全边界。"""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class SessionTests(unittest.TestCase):
    def test_signed_session_expires_after_180_days_and_invalidates_on_rotation(self):
        from dashboard.session import COOKIE_AGE, issue_cookie, valid_cookie

        self.assertEqual(COOKIE_AGE, 180 * 24 * 60 * 60)
        cookie = issue_cookie("s" * 64, "ComplexPassphrase5!x", now=1000)
        self.assertTrue(valid_cookie(cookie, "s" * 64, "ComplexPassphrase5!x", now=1000 + COOKIE_AGE - 1))
        self.assertFalse(valid_cookie(cookie, "s" * 64, "ComplexPassphrase5!x", now=1000 + COOKIE_AGE))
        self.assertFalse(valid_cookie(cookie, "t" * 64, "ComplexPassphrase5!x", now=1001))
        self.assertFalse(valid_cookie(cookie, "s" * 64, "ChangedPassphrase5!x", now=1001))
        self.assertFalse(valid_cookie(cookie[:-1] + ("0" if cookie[-1] != "0" else "1"),
                                      "s" * 64, "ComplexPassphrase5!x", now=1001))
        self.assertFalse(valid_cookie("", "s" * 64, "ComplexPassphrase5!x", now=1001))

    def test_login_has_one_failure_response_and_cookie_protects_only_reading(self):
        from dashboard.api import create_app
        from dashboard.store import register_project

        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / "progress.sqlite3")
            (Path(folder) / "index.html").write_text("live dashboard", encoding="utf-8")
            (Path(folder) / "login.html").write_text("login form", encoding="utf-8")
            app = create_app(db, folder, "test-viewer", "ComplexPassphrase5!x", "s" * 64)
            register_project(db, "one", "project-secret")
            with TestClient(app, base_url="https://testserver") as client:
                self.assertEqual(client.get("/", follow_redirects=False).status_code, 303)
                self.assertEqual(client.get("/api/v1/projects").status_code, 401)
                self.assertNotIn("www-authenticate", client.get("/api/v1/projects").headers)
                self.assertEqual(client.get("/login").text, "login form")
                self.assertEqual(client.get("/healthz").status_code, 200)
                self.assertEqual(client.get("/openapi.json").status_code, 200)
                schema = client.get("/openapi.json").json()
                login_contract = schema["paths"]["/api/v1/login"]["post"]
                self.assertEqual(login_contract["security"], [])
                self.assertEqual(login_contract["responses"]["404"]["content"]["text/plain"]["schema"]["const"],
                                 "功能未开发")
                self.assertIn("LoginRequest", schema["components"]["schemas"])

                failures = [client.post("/api/v1/login", json={"username": "wrong", "password": "ComplexPassphrase5!x"}),
                            client.post("/api/v1/login", json={"username": "test-viewer", "password": "wrong"}),
                            client.post("/api/v1/login", content=b"not-json"),
                            client.post("/api/v1/login", json={"username": "test-viewer"}),
                            client.post("/api/v1/login", json={"username": "test-viewer", "password": "x" * 5000}),
                            client.post("/api/v1/login", data={"username": "test-viewer", "password": "x"}),
                            client.post("/api/v1/login", content=b'{"username":"\\ud800","password":"x"}',
                                        headers={"Content-Type": "application/json"}),
                            client.post("/api/v1/login", content=b"[" * 3000,
                                        headers={"Content-Type": "application/json"}),
                            client.get("/api/v1/login"),
                            client.put("/api/v1/login")]
                self.assertEqual([(r.status_code, r.text) for r in failures], [(404, "功能未开发")] * len(failures))
                self.assertTrue(all("www-authenticate" not in r.headers for r in failures))

                revision = client.get("/api/v1/projects/one/revision", headers={"X-Project-Token": "project-secret"})
                self.assertEqual(revision.status_code, 200)
                self.assertEqual(revision.json()["revision"], 0)
                self.assertEqual(client.get("/api/v1/projects/one/revision").status_code, 401)

                success = client.post("/api/v1/login", json={"username": "test-viewer",
                                                              "password": "ComplexPassphrase5!x"})
                self.assertEqual(success.status_code, 200)
                cookie = success.headers["set-cookie"].lower()
                for required in ("__host-ai_dashboard_session=", "max-age=15552000", "secure", "httponly",
                                 "samesite=lax", "path=/"):
                    self.assertIn(required, cookie)
                self.assertNotIn("domain=", cookie)
                self.assertEqual(client.get("/api/v1/projects").status_code, 200)
                self.assertEqual(client.put("/api/v1/projects/one/snapshot", json={}).status_code, 401)

            with TestClient(app, base_url="https://testserver") as reporter:
                snapshot = {"schema_version": 1, "expected_revision": 0,
                            "observed_at": "2026-09-29T08:00:00Z", "change_note": "完成验证",
                            "project": {"name": "示例项目", "status": "active", "waves": [
                                {"id": "w", "name": "实现", "tasks": [{"id": "t", "title": "接口",
                                    "status": "done", "verified": True,
                                    "evidence": [{"label": "检查", "text": "通过"}]}]}]}}
                response = reporter.put("/api/v1/projects/one/snapshot", json=snapshot,
                                        headers={"X-Project-Token": "project-secret", "Idempotency-Key": "new-key"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(reporter.get("/api/v1/projects").status_code, 401)
                self.assertEqual(reporter.get("/api/v1/projects/one", headers={
                    "X-Project-Token": "project-secret"}).status_code, 200)
                self.assertEqual(reporter.get("/api/v1/projects/one", headers={
                    "X-Project-Token": "wrong"}).status_code, 401)
