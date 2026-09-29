"""统一看板服务入口。"""

import argparse
import os
from pathlib import Path

import uvicorn

from .api import create_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="启动统一看板服务（旧 --role read/write 已废弃）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    if args.host != "127.0.0.1":
        parser.error("服务仅允许绑定 127.0.0.1")
    db_path = os.environ.get("DASHBOARD_DB_PATH", ".runtime/dashboard.sqlite3")
    app = create_app(
        db_path, Path(os.environ.get("DASHBOARD_WEB_DIR", "web")),
        os.environ.get("DASHBOARD_LOGIN_USERNAME", ""),
        os.environ.get("DASHBOARD_LOGIN_PASSWORD", ""),
        os.environ.get("DASHBOARD_SESSION_SECRET", ""),
    )
    uvicorn.run(app, host=args.host, port=args.port or 8810, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
