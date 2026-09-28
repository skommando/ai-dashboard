"""完全分离的只读与上报 ASGI 应用。"""

import base64
import binascii
import hmac
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from .models import Snapshot
from .store import (AuthenticationChanged, KeyConflict, RevisionConflict,
                    authorized_revision, init_db, project_views, save_snapshot)


MAX_BODY = 1024 * 1024
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
BEARER_SECURITY = [{"ProjectBearer": []}]


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


def bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    parts = auth.split(" ", 1)
    return parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] else None


def create_write_app(db_path: str) -> FastAPI:
    init_db(db_path)
    app = FastAPI(title="AI Dashboard 上报 API", version="1.0.0")
    app.add_exception_handler(sqlite3.Error, storage_error)

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/projects/{project_id}/revision",
             openapi_extra={"security": BEARER_SECURITY},
             responses={401: {"description": "无效项目令牌"}})
    def revision(project_id: str, request: Request):
        token = bearer(request)
        if not ID_PATTERN.fullmatch(project_id) or token is None:
            return error(401, "unauthorized", "invalid project token")
        current = authorized_revision(db_path, project_id, token)
        if current is None:
            return error(401, "unauthorized", "invalid project token")
        return {"project_id": project_id, "revision": current}

    @app.put(
        "/api/v1/projects/{project_id}/snapshot",
        openapi_extra={
            "security": BEARER_SECURITY,
            "parameters": [{"name": "Idempotency-Key", "in": "header", "required": True,
                            "description": "同一请求重试时保持不变的唯一键",
                            "schema": {"type": "string", "minLength": 1, "maxLength": 128,
                                       "pattern": KEY_PATTERN.pattern}}],
            "requestBody": {"required": True, "content": {"application/json":
                            {"schema": {"$ref": "#/components/schemas/Snapshot"}}}},
        },
        responses={401: {"description": "无效项目令牌"},
                   409: {"description": "revision 或幂等键冲突"},
                   413: {"description": "请求体超过 1 MiB"},
                   422: {"description": "快照验证失败"}},
    )
    async def upload(project_id: str, request: Request):
        token = bearer(request)
        if not ID_PATTERN.fullmatch(project_id) or token is None:
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
            components.setdefault("securitySchemes", {})["ProjectBearer"] = {
                "type": "http", "scheme": "bearer"
            }
            schemas = components.setdefault("schemas", {})
            snapshot_schema = Snapshot.model_json_schema(ref_template="#/components/schemas/{model}")
            schemas.update(snapshot_schema.pop("$defs", {}))
            schemas["Snapshot"] = snapshot_schema
            app.openapi_schema = document
        return app.openapi_schema

    app.openapi = openapi
    return app


def _valid_basic(request: Request, username: str, password: str) -> bool:
    auth = request.headers.get("authorization", "")
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(parts[1], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    supplied_user, separator, supplied_password = decoded.partition(":")
    if not separator:
        return False
    user_matches = hmac.compare_digest(supplied_user.encode("utf-8"), username.encode("utf-8"))
    password_matches = hmac.compare_digest(supplied_password.encode("utf-8"), password.encode("utf-8"))
    return user_matches and password_matches


def create_read_app(db_path: str, web_dir: str | Path, username: str, password: str) -> FastAPI:
    if not username or not password:
        raise ValueError("view Basic Auth credentials are required")
    init_db(db_path)
    page = Path(web_dir) / "index.html"
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.add_exception_handler(sqlite3.Error, storage_error)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if not _valid_basic(request, username, password):
            response = error(401, "unauthorized", "Basic authentication required")
            response.headers["WWW-Authenticate"] = 'Basic realm="AI Dashboard", charset="UTF-8"'
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        if not page.is_file():
            return error(503, "web_unavailable", "web frontend is unavailable")
        return FileResponse(page, media_type="text/html; charset=utf-8")

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/projects")
    def projects():
        return {"projects": project_views(db_path), "server_time": now_iso()}

    @app.get("/api/v1/projects/{project_id}")
    def project(project_id: str):
        views = project_views(db_path, project_id)
        if not views:
            return error(404, "not_found", "project snapshot not found")
        return views[0]

    return app
