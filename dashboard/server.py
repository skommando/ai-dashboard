"""读写服务独立进程入口。"""

import argparse
import os
from pathlib import Path

import uvicorn

from .api import create_read_app, create_write_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="启动本机看板读取或上报服务")
    parser.add_argument("--role", choices=("read", "write"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    if args.host != "127.0.0.1":
        parser.error("服务仅允许绑定 127.0.0.1")
    db_path = os.environ.get("DASHBOARD_DB_PATH", ".runtime/dashboard.sqlite3")
    if args.role == "read":
        app = create_read_app(
            db_path, Path(os.environ.get("DASHBOARD_WEB_DIR", "web")),
            os.environ.get("DASHBOARD_VIEW_USERNAME", ""),
            os.environ.get("DASHBOARD_VIEW_PASSWORD", ""),
        )
    else:
        app = create_write_app(db_path)
    uvicorn.run(app, host=args.host, port=args.port or (8810 if args.role == "read" else 8811),
                access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
