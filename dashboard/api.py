"""统一读取与上报 ASGI 应用。"""

import hashlib
import hmac
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, ValidationError

from .models import Project, Snapshot
from .session import COOKIE_AGE, COOKIE_NAME, issue_cookie, valid_cookie
from .store import (AuthenticationChanged, KeyConflict, RevisionConflict,
                    authorized_revision, init_db, project_views, save_snapshot)


MAX_BODY = 1024 * 1024
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
READ_SECURITY = [{"ViewerSession": []}]
WRITE_SECURITY = [{"ProjectToken": []}]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
    current_revision: int | None = None


class HealthResponse(BaseModel):
    status: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginSuccess(BaseModel):
    status: str


class RevisionResponse(BaseModel):
    project_id: str
    revision: int


class SnapshotReceipt(BaseModel):
    project_id: str
    revision: int
    received_at: str
    replayed: bool


class ProgressResponse(BaseModel):
    done: int
    total: int
    percent: int | None
    unplannedWaves: int
    pendingAcceptance: int


class ProjectView(Project):
    id: str
    revision: int
    receivedAt: str
    observedAt: str
    progress: ProgressResponse


class ProjectsResponse(BaseModel):
    projects: list[ProjectView]
    server_time: str


def error_responses(*statuses: int) -> dict:
    descriptions = {401: "认证失败", 404: "项目快照不存在", 409: "版本或幂等键冲突",
                    413: "请求体超过 1 MiB", 415: "仅接受 application/json",
                    422: "输入验证失败", 500: "存储暂不可用", 503: "前端不可用"}
    return {status: {"model": ErrorResponse, "description": descriptions[status]} for status in statuses}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}, **extra}, status_code=status)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def storage_error(request: Request, exception: sqlite3.Error) -> JSONResponse:
    return error(500, "storage_error", "dashboard storage is temporarily unavailable")


def create_app(db_path: str, web_dir: str | Path, username: str, password: str,
               session_secret: str) -> FastAPI:
    if not username or not password or len(session_secret) < 32:
        raise ValueError("login username/password and a strong session secret are required")
    init_db(db_path)
    page = Path(web_dir) / "index.html"
    login_page = Path(web_dir) / "login.html"
    app = FastAPI(title="AI Dashboard API", version="1.0.0")
    app.add_exception_handler(sqlite3.Error, storage_error)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        path = request.url.path
        public = path in ("/healthz", "/docs", "/openapi.json", "/login", "/api/v1/login")
        token_route = (path.startswith("/api/v1/projects/") and
                       ((request.method == "GET" and path.endswith("/revision")) or
                        (request.method == "PUT" and path.endswith("/snapshot"))))
        own_project = re.fullmatch(r"/api/v1/projects/([A-Za-z0-9][A-Za-z0-9._-]{0,79})", path)
        own_read = (request.method == "GET" and own_project is not None and
                    authorized_revision(db_path, own_project.group(1), request.headers.get("x-project-token", ""))
                    is not None)
        if public or token_route or own_read or valid_cookie(request.cookies.get(COOKIE_NAME), session_secret, password):
            response = await call_next(request)
        elif path == "/" and request.method == "GET":
            response = RedirectResponse("/login", status_code=303)
        else:
            response = error(401, "unauthorized", "login required")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz", response_model=HealthResponse, responses=error_responses(500))
    def health():
        return {"status": "ok"}

    @app.get("/login", include_in_schema=False)
    def login_form():
        if not login_page.is_file():
            return error(503, "web_unavailable", "login frontend is unavailable")
        return FileResponse(login_page, media_type="text/html; charset=utf-8")

    @app.api_route("/api/v1/login", methods=["GET", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
                   include_in_schema=False)
    def unsupported_login():
        return PlainTextResponse("功能未开发", status_code=404)

    @app.post("/api/v1/login", response_model=LoginSuccess,
              openapi_extra={"security": [], "requestBody": {"required": True, "content": {
                  "application/json": {"schema": {"$ref": "#/components/schemas/LoginRequest"}}}}},
              responses={404: {"description": "登录未成功，固定正文功能未开发",
                               "content": {"text/plain": {"schema": {"type": "string", "const": "功能未开发"}}}}})
    async def login(request: Request):
        failure = PlainTextResponse("功能未开发", status_code=404)
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            return failure
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return failure
        try:
            payload = json.loads(body, object_pairs_hook=unique_pairs)
        except (ValueError, UnicodeDecodeError, RecursionError):
            return failure
        if (not isinstance(payload, dict) or set(payload) != {"username", "password"}
                or not all(isinstance(value, str) for value in payload.values())):
            return failure
        try:
            supplied_user = hashlib.sha256(payload["username"].encode("utf-8")).digest()
            expected_user = hashlib.sha256(username.encode("utf-8")).digest()
            supplied_password = hashlib.sha256(payload["password"].encode("utf-8")).digest()
            expected_password = hashlib.sha256(password.encode("utf-8")).digest()
        except UnicodeEncodeError:
            return failure
        if not (hmac.compare_digest(supplied_user, expected_user) &
                hmac.compare_digest(supplied_password, expected_password)):
            return failure
        response = JSONResponse({"status": "ok"})
        response.set_cookie(COOKIE_NAME, issue_cookie(session_secret, password), max_age=COOKIE_AGE,
                            secure=True, httponly=True, samesite="lax", path="/")
        return response

    @app.get("/api/v1/projects/{project_id}/revision",
             response_model=RevisionResponse,
             openapi_extra={"security": WRITE_SECURITY},
             responses=error_responses(401, 500))
    def revision(project_id: str, request: Request):
        token = request.headers.get("x-project-token", "")
        if not ID_PATTERN.fullmatch(project_id) or not token:
            return error(401, "unauthorized", "invalid project token")
        current = authorized_revision(db_path, project_id, token)
        if current is None:
            return error(401, "unauthorized", "invalid project token")
        return {"project_id": project_id, "revision": current}

    @app.put(
        "/api/v1/projects/{project_id}/snapshot",
        response_model=SnapshotReceipt,
        openapi_extra={
            "security": WRITE_SECURITY,
            "parameters": [{"name": "Idempotency-Key", "in": "header", "required": True,
                            "description": "同一请求重试时保持不变的唯一键",
                            "schema": {"type": "string", "minLength": 1, "maxLength": 128,
                                       "pattern": KEY_PATTERN.pattern}}],
            "requestBody": {"required": True, "content": {"application/json":
                            {"schema": {"$ref": "#/components/schemas/Snapshot"}}}},
        },
        responses=error_responses(401, 409, 413, 415, 422, 500),
    )
    async def upload(project_id: str, request: Request):
        token = request.headers.get("x-project-token", "")
        if not ID_PATTERN.fullmatch(project_id) or not token:
            return error(401, "unauthorized", "invalid project token")
        if authorized_revision(db_path, project_id, token) is None:
            return error(401, "unauthorized", "invalid project token")
        key = request.headers.get("idempotency-key", "")
        if not KEY_PATTERN.fullmatch(key):
            return error(422, "invalid_key", "Idempotency-Key must be a stable 1-128 character identifier")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return error(415, "unsupported_media_type", "Content-Type must be application/json")
        size = 0
        body = bytearray()
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY:
                return error(413, "body_too_large", "snapshot exceeds 1 MiB")
            body.extend(chunk)
        try:
            payload = json.loads(body, object_pairs_hook=unique_pairs)
            snapshot = Snapshot.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError):
            return error(422, "invalid_snapshot", "snapshot failed validation")
        try:
            result = save_snapshot(db_path, project_id, token, key, snapshot)
        except AuthenticationChanged:
            return error(401, "unauthorized", "invalid project token")
        except KeyConflict:
            return error(409, "idempotency_conflict", "key already used for a different request")
        except RevisionConflict as conflict:
            return error(409, "revision_conflict", "expected_revision differs from current revision",
                         current_revision=conflict.current_revision)
        return result

    def openapi():
        if app.openapi_schema is None:
            document = get_openapi(title=app.title, version=app.version, routes=app.routes)
            components = document.setdefault("components", {})
            components.setdefault("securitySchemes", {}).update({
                "ViewerSession": {"type": "apiKey", "in": "cookie", "name": COOKIE_NAME},
                "ProjectToken": {"type": "apiKey", "in": "header", "name": "X-Project-Token"},
            })
            schemas = components.setdefault("schemas", {})
            snapshot_schema = Snapshot.model_json_schema(ref_template="#/components/schemas/{model}")
            schemas.update(snapshot_schema.pop("$defs", {}))
            schemas["Snapshot"] = snapshot_schema
            schemas["LoginRequest"] = LoginRequest.model_json_schema()
            for path, method in (("/api/v1/projects/{project_id}", "get"),
                                 ("/api/v1/projects/{project_id}/revision", "get"),
                                 ("/api/v1/projects/{project_id}/snapshot", "put")):
                operation = document["paths"][path][method]
                project_id = next(parameter for parameter in operation["parameters"]
                                  if parameter["in"] == "path" and parameter["name"] == "project_id")
                project_id["schema"].update({"minLength": 1, "maxLength": 80,
                                             "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"})
            for method, path in (("get", "/api/v1/projects/{project_id}/revision"),
                                 ("put", "/api/v1/projects/{project_id}/snapshot")):
                document["paths"][path][method]["responses"]["401"]["description"] = (
                    "project_id 或项目令牌无效")
            document["paths"]["/api/v1/projects/{project_id}/revision"]["get"]["responses"]["422"]["description"] = (
                "框架请求参数校验失败；无效 project_id 按 401 返回")
            app.openapi_schema = document
        return app.openapi_schema

    app.openapi = openapi

    @app.get("/", openapi_extra={"security": READ_SECURITY}, responses=error_responses(401, 503))
    def index():
        if not page.is_file():
            return error(503, "web_unavailable", "web frontend is unavailable")
        return FileResponse(page, media_type="text/html; charset=utf-8")

    @app.get("/api/v1/projects", response_model=ProjectsResponse,
             openapi_extra={"security": READ_SECURITY}, responses=error_responses(401, 500))
    def projects():
        return {"projects": project_views(db_path), "server_time": now_iso()}

    @app.get("/api/v1/projects/{project_id}", response_model=ProjectView,
             openapi_extra={"security": READ_SECURITY + WRITE_SECURITY}, responses=error_responses(401, 404, 500))
    def project(project_id: str):
        views = project_views(db_path, project_id)
        if not views:
            return error(404, "not_found", "project snapshot not found")
        return views[0]

    return app
