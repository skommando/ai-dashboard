"""本地项目登记与显式令牌轮换。原始令牌只写入指定文件。"""

import argparse
import os
import re
import secrets
import sqlite3
import sys
from pathlib import Path

from .store import init_db, register_project, rotate_project


ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
DEFAULT_DB = ".runtime/dashboard.sqlite3"


def _new_token_file(path: Path) -> str:
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(token + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.chmod(path, 0o600)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return token


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="初始化数据库、登记项目或显式轮换上报令牌")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "register", "rotate"):
        command = commands.add_parser(name)
        if name != "init":
            command.add_argument("project_id")
            command.add_argument("--token-file", required=True, type=Path)
        command.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args(argv)
    if args.command != "init" and not ID_PATTERN.fullmatch(args.project_id):
        print("项目 ID 必须为 1-80 位字母、数字、点、横线或下划线，且首位为字母或数字", file=sys.stderr)
        return 2
    try:
        init_db(args.db)
        if args.command == "init":
            print("数据库已初始化")
            return 0
        token = _new_token_file(args.token_file)
        try:
            if args.command == "register":
                register_project(args.db, args.project_id, token)
            else:
                rotate_project(args.db, args.project_id, token)
        except BaseException:
            args.token_file.unlink(missing_ok=True)
            raise
    except FileExistsError:
        print("令牌文件已存在；请选择新的文件路径", file=sys.stderr)
        return 2
    except sqlite3.IntegrityError:
        print("项目已登记；如需更换令牌，请显式执行 rotate", file=sys.stderr)
        return 2
    except KeyError:
        print("项目尚未登记", file=sys.stderr)
        return 2
    print("项目已登记" if args.command == "register" else "令牌已轮换")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
