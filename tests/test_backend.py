import copy
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient


def snapshot():
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "observed_at": "2026-09-28T08:00:00Z",
        "change_note": "完成接入验证",
        "project": {
            "name": "项目名称", "shortName": "短名称", "description": "目标",
            "summary": "进展", "status": "active", "acceptance": "not_required",
            "category": "个人工具", "glyph": "book", "color": "sage",
            "currentWave": "wave-implementation",
            "waves": [{"id": "wave-implementation", "name": "实现", "defined": True,
                       "acceptance": "not_required", "tasks": [
                           {"id": "task-api", "code": "API-01", "title": "实现接口",
                            "status": "done", "verified": True,
                            "acceptance": "not_required", "goal": "稳定接收",
                            "summary": "检查通过", "updatedAt": "2026-09-28T08:00:00Z",
                            "evidence": [{"label": "检查", "text": "接口回归通过"}],
                            "children": [{"title": "输入校验", "status": "done"}]}]}],
            "updates": [{"at": "2026-09-28T08:00:00Z", "tone": "done",
                         "text": "检查通过", "detail": "API-01"}],
        },
    }


class BackendContractTests(unittest.TestCase):
    def setUp(self):
        from dashboard.store import init_db, register_project
        from dashboard.api import create_read_app, create_write_app

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "dashboard.sqlite3")
        self.web = Path(self.temp.name) / "web"
        self.web.mkdir()
        (self.web / "index.html").write_text("real front end", encoding="utf-8")
        init_db(self.db)
        self.token = "project-one-secret"
        self.other_token = "project-two-secret"
        register_project(self.db, "one", self.token)
        register_project(self.db, "two", self.other_token)
        self.write = TestClient(create_write_app(self.db))
        self.read = TestClient(create_read_app(self.db, self.web, "viewer", "view-secret"))

    def send(self, payload=None, key="request-1", token=None, project="one"):
        return self.write.put(
            f"/api/v1/projects/{project}/snapshot",
            headers={"Authorization": f"Bearer {token or self.token}",
                     "Idempotency-Key": key},
            json=snapshot() if payload is None else payload,
        )

    def view(self, path="/api/v1/projects", password="view-secret"):
        return self.read.get(path, auth=("viewer", password))

    def test_empty_read_is_authenticated_and_no_write_routes_exist(self):
        self.assertEqual(self.read.get("/api/v1/projects").status_code, 401)
        self.assertEqual(self.read.get("/healthz").status_code, 401)
        self.assertEqual(self.view(password="wrong").status_code, 401)
        self.assertEqual(self.read.get("/openapi.json", auth=("viewer", "view-secret")).status_code, 404)
        self.assertEqual(self.read.get("/docs", auth=("viewer", "view-secret")).status_code, 404)
        self.assertEqual(self.read.put("/api/v1/projects/one/snapshot", auth=("viewer", "view-secret")).status_code, 404)
        response = self.view()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["projects"], [])
        self.assertIn("server_time", response.json())
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.view("/").text, "real front end")
        schema = self.write.get("/openapi.json").json()
        self.assertIn("put", schema["paths"]["/api/v1/projects/{project_id}/snapshot"])

    def test_atomic_snapshot_progress_and_replay_survive_restart(self):
        response = self.send()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["revision"], 1)
        view = self.view().json()["projects"][0]
        self.assertEqual(view["id"], "one")
        self.assertEqual(view["progress"], {"done": 1, "total": 1, "percent": 100,
                                            "unplannedWaves": 0, "pendingAcceptance": 0})
        self.assertEqual(view["observedAt"], "2026-09-28T08:00:00Z")
        self.assertIn("receivedAt", view)
        self.assertNotIn("token", json.dumps(view).lower())
        from dashboard.api import create_write_app
        restarted = TestClient(create_write_app(self.db))
        replay = restarted.put("/api/v1/projects/one/snapshot",
                              headers={"Authorization": f"Bearer {self.token}",
                                       "Idempotency-Key": "request-1"}, json=snapshot())
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["revision"], 1)
        self.assertTrue(replay.json()["replayed"])
        db = sqlite3.connect(self.db)
        try:
            self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
        finally:
            db.close()

    def test_cas_two_writers_and_replay_after_later_revision(self):
        def send_key(key):
            return self.send(key=key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send_key, ["writer-a", "writer-b"]))
        self.assertEqual(sorted(result.status_code for result in results), [200, 409])
        self.assertEqual(next(r for r in results if r.status_code == 409).json()["current_revision"], 1)
        winner = "writer-a" if results[0].status_code == 200 else "writer-b"
        second = snapshot()
        second["expected_revision"] = 1
        second["project"]["summary"] = "第二次"
        self.assertEqual(self.send(second, "later").json()["revision"], 2)
        replay = self.send(key=winner)
        self.assertEqual(replay.json()["revision"], 1)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(self.view().json()["projects"][0]["summary"], "第二次")

    def test_same_key_different_content_and_cross_project_token_rejected(self):
        self.assertEqual(self.send().status_code, 200)
        changed = snapshot()
        changed["project"]["summary"] = "changed"
        self.assertEqual(self.send(changed).status_code, 409)
        self.assertEqual(self.send(token=self.other_token).status_code, 401)
        self.assertEqual(self.send(project="two", token=self.other_token).status_code, 200)
        self.assertEqual(self.write.get("/api/v1/projects/one/revision",
                                        headers={"Authorization": f"Bearer {self.other_token}"}).status_code, 401)

    def test_invalid_snapshots_do_not_partially_write(self):
        cases = []
        p = snapshot(); p["project"]["waves"][0]["tasks"][0]["verified"] = False; cases.append(p)
        p = snapshot(); p["project"]["waves"][0]["tasks"][0]["evidence"] = []; cases.append(p)
        p = snapshot(); p["project"]["waves"][0]["tasks"][0]["evidence"] = [{"label": "", "text": " "}]; cases.append(p)
        p = snapshot(); p["project"]["unknown"] = "x"; cases.append(p)
        p = snapshot(); p["project"]["waves"].append(copy.deepcopy(p["project"]["waves"][0])); cases.append(p)
        p = snapshot(); p["project"]["currentWave"] = "missing"; cases.append(p)
        p = snapshot(); p["observed_at"] = "2026-09-28T08:00:00"; cases.append(p)
        p = snapshot(); p["schema_version"] = 2; cases.append(p)
        p = snapshot(); p["project"]["waves"][0]["defined"] = False; cases.append(p)
        for index, case in enumerate(cases):
            with self.subTest(index=index):
                response = self.send(case, key=f"bad-{index}")
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.view().json()["projects"], [])
        self.assertEqual(self.write.get("/api/v1/projects/one/revision",
                                        headers={"Authorization": f"Bearer {self.token}"}).json()["revision"], 0)

    def test_body_limit_and_complete_requirements(self):
        huge = b" " * (1024 * 1024 + 1)
        response = self.write.put("/api/v1/projects/one/snapshot",
                                  headers={"Authorization": f"Bearer {self.token}",
                                           "Idempotency-Key": "huge",
                                           "Content-Type": "application/json"}, content=huge)
        self.assertEqual(response.status_code, 413)
        empty_complete = snapshot()
        empty_complete["project"].update(status="complete", waves=[], currentWave=None)
        self.assertEqual(self.send(empty_complete, "complete-empty").status_code, 422)
        pending = snapshot()
        pending["project"].update(status="complete", acceptance="pending")
        self.assertEqual(self.send(pending, "complete-pending").status_code, 422)
        rejected = snapshot()
        rejected["project"].update(status="complete", acceptance="rejected")
        self.assertEqual(self.send(rejected, "complete-rejected").status_code, 422)

    def test_duplicate_json_key_is_rejected_without_write(self):
        raw = json.dumps(snapshot(), ensure_ascii=False)
        raw = raw.replace('"expected_revision": 0', '"expected_revision": 99, "expected_revision": 0', 1)
        response = self.write.put("/api/v1/projects/one/snapshot",
                                  headers={"Authorization": f"Bearer {self.token}",
                                           "Idempotency-Key": "duplicate-json",
                                           "Content-Type": "application/json"},
                                  content=raw.encode("utf-8"))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.view().json()["projects"], [])

    def test_storage_error_has_structured_response_without_local_details(self):
        db = sqlite3.connect(self.db)
        try:
            db.execute("DROP TABLE receipts")
            db.commit()
        finally:
            db.close()
        response = self.send()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "storage_error")
        self.assertNotIn("receipts", response.text)
        self.assertNotIn(self.db, response.text)


if __name__ == "__main__":
    unittest.main()
