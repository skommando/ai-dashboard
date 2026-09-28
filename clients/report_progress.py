"""标准库上报客户端：先封存请求，再用同一键和内容安全重试。"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class ReportError(Exception):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def urlopen(request, timeout):
    return build_opener(ProxyHandler({}), NoRedirects()).open(request, timeout=timeout)


def prepare_request(project_id: str, snapshot_file: Path, request_file: Path,
                    idempotency_key: str | None = None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", project_id):
        raise ReportError("无效项目 ID")
    key = idempotency_key or str(uuid.uuid4())
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", key):
        raise ReportError("无效幂等键")
    snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    envelope = {"project_id": project_id, "idempotency_key": key, "snapshot": snapshot}
    request_file.parent.mkdir(parents=True, exist_ok=True)
    with request_file.open("x", encoding="utf-8") as file:
        json.dump(envelope, file, ensure_ascii=False, indent=2)
        file.write("\n")


def send_request(request_file: Path, token: str, base_url: str = "http://127.0.0.1:8811",
                 retries: int = 4) -> dict:
    envelope = json.loads(request_file.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or set(envelope) != {"project_id", "idempotency_key", "snapshot"}:
        raise ReportError("请求文件格式无效")
    if (not isinstance(envelope["project_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", envelope["project_id"])
            or not isinstance(envelope["idempotency_key"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", envelope["idempotency_key"])):
        raise ReportError("请求文件标识无效")
    parsed = urlsplit(base_url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise ReportError("写入地址必须为本机 http://127.0.0.1:端口")
    try:
        port = parsed.port
    except ValueError:
        raise ReportError("写入端口无效") from None
    if port is None:
        raise ReportError("写入端口必须明确指定")
    body = json.dumps(envelope["snapshot"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    url = base_url.rstrip("/") + "/api/v1/projects/" + quote(envelope["project_id"], safe="") + "/snapshot"
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": envelope["idempotency_key"],
               "Content-Type": "application/json"}
    for attempt in range(retries + 1):
        request = Request(url, data=body, headers=headers, method="PUT")
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            if 500 <= exc.code <= 599 and attempt < retries:
                time.sleep(min(0.5 * 2 ** attempt, 8))
                continue
            if exc.code == 409:
                try:
                    current = json.load(exc).get("current_revision")
                except (ValueError, OSError):
                    current = None
                detail = f"；当前 revision={current}" if current is not None else ""
                raise ReportError("409 冲突" + detail + "。请人工检查最新快照后创建新请求文件") from None
            raise ReportError(f"上报失败：HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            if attempt >= retries:
                raise ReportError("网络故障；请求文件可原样重试") from None
            time.sleep(min(0.5 * 2 ** attempt, 8))
    raise AssertionError("unreachable")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="封存并上报进度快照")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("project_id")
    prepare.add_argument("--snapshot", type=Path, required=True)
    prepare.add_argument("--request-file", type=Path, required=True)
    prepare.add_argument("--idempotency-key")
    send = commands.add_parser("send")
    send.add_argument("--request-file", type=Path, required=True)
    credential = send.add_mutually_exclusive_group(required=True)
    credential.add_argument("--token-file", type=Path)
    credential.add_argument("--token-env")
    send.add_argument("--base-url", default="http://127.0.0.1:8811")
    send.add_argument("--retries", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare_request(args.project_id, args.snapshot, args.request_file, args.idempotency_key)
            print("请求已封存；失败后使用同一请求文件重试")
        else:
            if args.retries < 0 or args.retries > 10:
                raise ReportError("retries 必须在 0-10 之间")
            token = (args.token_file.read_text(encoding="utf-8").strip()
                     if args.token_file else os.environ.get(args.token_env, ""))
            if not token:
                raise ReportError("上报令牌为空")
            result = send_request(args.request_file, token, args.base_url, args.retries)
            print(f"上报成功，revision={result['revision']}，replayed={str(result['replayed']).lower()}")
    except (ReportError, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, ReportError):
            print(str(exc), file=sys.stderr)
        else:
            print("无法读取或处理请求文件", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
