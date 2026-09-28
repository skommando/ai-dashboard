"""Run the local release gate and record any explicitly authorized test skip."""

import argparse
from datetime import datetime, timezone
import glob
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")


def default_record(sha):
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if not base:
        base = str(Path.home() / ".local" / "state")
    return Path(base) / "ai-dashboard" / "release-checks" / (sha + ".json")


def command(args):
    result = subprocess.run(args, cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError("检查未通过：" + Path(args[0]).name)


def check(sha, skip_tests=False, reason=None, record=None):
    if sys.version_info[:2] != (3, 12):
        raise ValueError("发布检查必须使用 Python 3.12")
    if not SHA.fullmatch(sha):
        raise ValueError("需要完整的 40 位小写 SHA")
    if skip_tests and not reason:
        raise ValueError("跳过测试必须提供 --reason")
    if reason and not skip_tests:
        raise ValueError("--reason 只能与 --skip-tests 配合使用")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if current != sha:
        raise ValueError("当前 HEAD 与指定 SHA 不一致")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                               cwd=ROOT, text=True).strip():
        raise ValueError("发布检查要求干净工作树")
    command(["node", "scripts/build-demo.cjs"])
    if not skip_tests:
        node_tests = sorted(glob.glob(str(ROOT / "tests" / "*.cjs")))
        if not node_tests:
            raise ValueError("找不到 Node 测试")
        command(["node", "--test", *node_tests])
        command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"])
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                               cwd=ROOT, text=True).strip():
        raise ValueError("构建或测试改变了工作树")
    destination = record or default_record(sha)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "sha": sha,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "build": "passed", "tests": "skipped" if skip_tests else "passed",
        "skip_reason": reason if skip_tests else None,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    print("检查记录：" + str(destination))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--reason")
    parser.add_argument("--record", type=Path)
    args = parser.parse_args(argv)
    try:
        check(args.sha, args.skip_tests, args.reason, args.record)
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
