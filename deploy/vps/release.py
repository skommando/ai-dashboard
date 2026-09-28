#!/usr/bin/env python3
"""Deploy one reviewed main commit without putting private data in Git.

Run as root on the VPS. The application source comes only from the supplied
public GitHub repository's main ref. Database backups are retained, never
automatically restored over later production writes.
"""

import argparse
import base64
from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


SHA = re.compile(r"[0-9a-f]{40}\Z")
ENV_KEYS = {"DASHBOARD_DB_PATH", "DASHBOARD_WEB_DIR",
            "DASHBOARD_VIEW_USERNAME", "DASHBOARD_VIEW_PASSWORD"}
UNIT = Path("/etc/systemd/system/ai-dashboard.service")
SOURCE = Path(__file__).resolve().parent


def validate_sha(value):
    if not SHA.fullmatch(value):
        raise ValueError("需要完整的 40 位小写 Git SHA")
    return value


def validate_repo_url(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname != "github.com"
            or parsed.port is not None or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", parsed.path)):
        raise ValueError("源码必须是无嵌入凭据的 GitHub HTTPS 仓库 URL")
    return value


def validate_path(path, no_space=False):
    path = Path(path)
    if (not path.is_absolute() or len(path.parts) <= 1
            or any(part in (".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", part)
                   for part in path.parts[1:])):
        raise ValueError("配置路径必须是安全绝对路径")
    return path


def server_has_basic(site_text):
    """Accept the existing one-server Nginx layout, not nested location auth."""
    depth = 0
    basic = user_file = tls = False
    for raw in site_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if depth == 1:
            match = re.fullmatch(r"auth_basic\s+([^;]+);", line)
            if match:
                basic = match.group(1).strip().lower() != "off"
            if re.fullmatch(r"auth_basic_user_file\s+[^;]+;", line):
                user_file = True
            if re.fullmatch(r"listen\s+443\b[^;]*;", line):
                tls = True
        depth += line.count("{") - line.count("}")
        if depth < 0:
            return False
    return depth == 0 and basic and user_file and tls


def read_environment(path):
    """Parse the supported systemd EnvironmentFile subset, without executing it."""
    import shlex

    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = shlex.split(line, comments=False, posix=True)
        if len(parts) != 1 or "=" not in parts[0]:
            raise ValueError("dashboard.env 格式无效")
        key, value = parts[0].split("=", 1)
        if key not in ENV_KEYS or key in values or not value or "\n" in value:
            raise ValueError("dashboard.env 字段无效")
        values[key] = value
    if set(values) != ENV_KEYS:
        raise ValueError("dashboard.env 缺少必需字段")
    return values


def atomic_symlink(link, target):
    if link.exists() and not link.is_symlink():
        raise ValueError("current 必须是符号链接")
    temporary = link.parent / (".current-" + uuid.uuid4().hex)
    temporary.symlink_to(target, target_is_directory=True)
    try:
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def run(*args, cwd=None, capture=False):
    result = subprocess.run(args, cwd=cwd, check=False, text=True,
                            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError("命令执行失败：" + Path(args[0]).name)
    return result.stdout.strip() if capture else ""


def backup_database(source, destination):
    uri = "file:" + urllib.parse.quote(str(source)) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as origin:
        with closing(sqlite3.connect(str(destination))) as backup:
            origin.backup(backup)
            result = backup.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError("SQLite 备份完整性检查失败")
    os.chmod(destination, 0o600)


def healthy(environment, attempts=20):
    credential = (environment["DASHBOARD_VIEW_USERNAME"] + ":"
                  + environment["DASHBOARD_VIEW_PASSWORD"]).encode("utf-8")
    authorization = "Basic " + base64.b64encode(credential).decode("ascii")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request("http://127.0.0.1:8810/healthz",
                                     headers={"Authorization": authorization})
    for _ in range(attempts):
        try:
            with opener.open(request, timeout=2) as response:
                if response.status == 200 and json.load(response).get("status") == "ok":
                    return True
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    return False


class Release:
    def __init__(self, root, unit=UNIT):
        self.root = Path(root)
        self.unit = Path(unit)
        self.repo = self.root / "repo"
        self.releases = self.root / "releases"
        self.shared = self.root / "shared"
        self.current = self.root / "current"
        self.environment_file = self.shared / "dashboard.env"
        self.database = self.shared / "data" / "dashboard.sqlite3"

    def preflight(self, site, include, site_root, nginx, python):
        import pwd
        validate_path(self.root, no_space=True)
        for path in (site, include, site_root, nginx, python):
            validate_path(path, no_space=path in (include, site_root))
        if os.geteuid() != 0:
            raise ValueError("必须以 root 运行")
        try:
            account = pwd.getpwnam("ai-dashboard")
        except KeyError as exc:
            raise ValueError("缺少 ai-dashboard 系统用户") from exc
        uid, gid = account.pw_uid, account.pw_gid
        for path in (site, site_root, nginx, self.environment_file, self.database):
            if path.is_symlink() or not path.exists():
                raise ValueError("前置路径缺失或为符号链接：" + str(path))
        if not python.exists():
            raise ValueError("Python 解释器不存在")
        if not site.is_file() or not nginx.is_file() or not python.is_file() or not self.database.is_file():
            raise ValueError("站点、解释器或数据库类型错误")
        if not site_root.is_dir() or (site_root / "dashboard-offline.html").is_symlink():
            raise ValueError("站点静态根目录或离线页路径无效")
        if include.is_symlink() or self.unit.is_symlink() or (self.current.exists() and not self.current.is_symlink()):
            raise ValueError("include、service 或 current 路径类型错误")
        if self.current.is_symlink():
            active = self.current.resolve(strict=True)
            if active.parent != self.releases or not SHA.fullmatch(active.name):
                raise ValueError("current 未指向受管理的 release")
        if self.root.is_symlink() or self.shared.is_symlink() or self.repo.is_symlink():
            raise ValueError("部署目录不能是符号链接")
        site_text = site.read_text(encoding="utf-8")
        if not server_has_basic(site_text):
            raise ValueError("站点须先配置 TLS 与 Basic Auth")
        version = run(str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])", capture=True)
        if version != "3.12":
            raise ValueError("外置解释器必须是 Python 3.12")
        environment = read_environment(self.environment_file)
        if (environment["DASHBOARD_DB_PATH"] != str(self.database)
                or environment["DASHBOARD_WEB_DIR"] != str(self.current / "web")):
            raise ValueError("dashboard.env 数据库或页面路径不符")
        if self.environment_file.stat().st_uid != 0 or self.environment_file.stat().st_mode & 0o137:
            raise ValueError("dashboard.env 须由 root 拥有且权限不宽于 0640")
        with closing(sqlite3.connect("file:" + urllib.parse.quote(str(self.database)) + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("生产数据库检查失败")
        return uid, gid, environment

    def layout(self, uid, gid):
        for path, mode, owner, group in (
                (self.root, 0o755, 0, 0), (self.repo, 0o700, 0, 0),
                (self.releases, 0o755, 0, 0), (self.shared, 0o750, 0, gid),
                (self.shared / "data", 0o700, uid, gid),
                (self.shared / "credentials", 0o700, 0, 0),
                (self.shared / "backups", 0o700, 0, 0)):
            if path.is_symlink():
                raise ValueError("部署目录不能是符号链接：" + str(path))
            path.mkdir(parents=True, exist_ok=True)
            os.chown(path, owner, group)
            os.chmod(path, mode)
        os.chown(self.environment_file, 0, gid)
        os.chmod(self.environment_file, 0o640)
        os.chown(self.database, uid, gid)
        os.chmod(self.database, 0o660)

    def backup(self, sha):
        folder = self.shared / "backups" / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + sha[:12] + "-" + uuid.uuid4().hex[:8])
        folder.mkdir(mode=0o700)
        backup_database(self.database, folder / "dashboard.sqlite3")
        return folder

    def fetch_main(self, url, sha):
        validate_repo_url(url)
        validate_sha(sha)
        remote_sha = run("git", "ls-remote", "--exit-code", url, "refs/heads/main", capture=True).split()[0]
        if remote_sha != sha:
            raise ValueError("SHA 与 GitHub main 当前提交不一致")
        if not (self.repo / "HEAD").exists():
            run("git", "init", "--bare", str(self.repo))
            run("git", "--git-dir=" + str(self.repo), "remote", "add", "origin", url)
        origin = run("git", "--git-dir=" + str(self.repo), "remote", "get-url", "origin", capture=True)
        if origin != url:
            raise ValueError("已有 repo 来源与指定 GitHub 仓库不一致")
        run("git", "--git-dir=" + str(self.repo), "fetch", "--no-tags", "origin",
            "refs/heads/main:refs/heads/main")
        fetched = run("git", "--git-dir=" + str(self.repo), "rev-parse", "refs/heads/main", capture=True)
        if fetched != sha:
            raise ValueError("拉取后 main 已变化；请重新审核 SHA")

    def validate_release(self, sha, require_ready=False):
        release = self.releases / sha
        if release.is_symlink() or not release.is_dir():
            raise ValueError("release 目录无效")
        checked = run("git", "-C", str(release), "rev-parse", "HEAD", capture=True)
        if checked != sha:
            raise ValueError("release SHA 不匹配")
        if run("git", "-C", str(release), "status", "--porcelain", "--untracked-files=all", capture=True):
            raise ValueError("release 源码存在改动或额外文件")
        for path in (release, release / "dashboard", release / "dashboard/server.py",
                     release / "web", release / "web/index.html", release / "requirements-lock.txt"):
            if path.is_symlink() or not path.exists():
                raise ValueError("release 关键源码路径无效")
            mode = path.stat()
            if (mode.st_uid != 0 or mode.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                    or not mode.st_mode & stat.S_IROTH
                    or path.is_dir() and not mode.st_mode & stat.S_IXOTH):
                raise ValueError("release 源码所有权或权限不安全")
        venv = release / ".venv"
        if venv.is_symlink():
            raise ValueError("release venv 不能是符号链接")
        ready = venv / ".dashboard-ready"
        if ready.exists() and ready.read_text(encoding="ascii").strip() != sha:
            raise ValueError("release venv 就绪标记与 SHA 不符")
        if require_ready and (not ready.is_file() or not (venv / "bin/python").is_file()):
            raise ValueError("release 尚未安装完成")
        return release

    def stage(self, sha, python):
        release = self.releases / sha
        if release.is_symlink():
            raise ValueError("release 不能是符号链接")
        if not release.exists():
            previous_umask = os.umask(0o022)
            try:
                run("git", "--git-dir=" + str(self.repo), "worktree", "add", "--detach", str(release), sha)
            finally:
                os.umask(previous_umask)
        self.validate_release(sha)
        venv = release / ".venv"
        ready = venv / ".dashboard-ready"
        if not ready.exists():
            previous_umask = os.umask(0o022)
            try:
                if not venv.exists():
                    run(str(python), "-m", "venv", str(venv))
                run(str(venv / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", str(release / "requirements-lock.txt"))
                run(str(venv / "bin/python"), "-m", "pip", "check")
                ready.write_text(sha + "\n", encoding="ascii")
            finally:
                os.umask(previous_umask)
        run(str(venv / "bin/python"), "-c", "import fastapi, uvicorn, dashboard", cwd=release)
        return release

    def configure_site(self, site, include, site_root):
        text = site.read_text(encoding="utf-8")
        directive = "include " + str(include) + ";"
        if directive not in text:
            if "#REWRITE-END" not in text:
                raise ValueError("站点没有可定位的 include 插入点")
            text = text.replace("#REWRITE-END", "#REWRITE-END\n    " + directive, 1)
            site.write_text(text, encoding="utf-8")
        template = (SOURCE / "view-dashboard.locations.conf").read_text(encoding="utf-8")
        if not site_root.is_absolute() or " " in str(site_root):
            raise ValueError("站点根目录须为无空格绝对路径")
        include.write_text(template.replace("@SITE_ROOT@", str(site_root)), encoding="utf-8")
        os.chmod(include, 0o644)
        offline = site_root / "dashboard-offline.html"
        shutil.copy2(SOURCE / "offline.html", offline)
        os.chmod(offline, 0o644)

    def install_unit(self):
        template = (SOURCE / "ai-dashboard.service.in").read_text(encoding="utf-8")
        content = template.replace("@ROOT@", str(self.root))
        temporary = self.unit.with_name(self.unit.name + ".tmp-" + uuid.uuid4().hex)
        temporary.write_text(content, encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, self.unit)

    def switch(self, release, environment):
        previous = self.current.resolve(strict=True) if self.current.is_symlink() else None
        atomic_symlink(self.current, release)
        run("systemctl", "daemon-reload")
        run("systemctl", "enable", "ai-dashboard.service")
        run("systemctl", "restart", "ai-dashboard.service")
        if not healthy(environment):
            raise RuntimeError("新服务健康检查失败")
        return previous

    def deploy(self, url, sha, python, site, include, site_root, nginx):
        uid, gid, environment = self.preflight(site, include, site_root, nginx, python)
        self.layout(uid, gid)
        # This lock covers source, symlink, service and Nginx changes.
        import fcntl
        lock = self.root / "release.lock"
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fetch_main(url, sha)
            release = self.stage(sha, python)
            backup = self.backup(sha)
            previous = self.current.resolve(strict=True) if self.current.is_symlink() else None
            was_enabled = subprocess.run(("systemctl", "is-enabled", "--quiet", "ai-dashboard.service"),
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            was_active = subprocess.run(("systemctl", "is-active", "--quiet", "ai-dashboard.service"),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            saved = {}
            for index, path in enumerate((site, include, site_root / "dashboard-offline.html", self.unit)):
                saved[path] = backup / ("file-" + str(index)) if path.exists() else None
                if saved[path] is not None:
                    shutil.copy2(path, saved[path])
            try:
                self.install_unit()
                self.switch(release, environment)
                self.configure_site(site, include, site_root)
                run(str(nginx), "-t")
                run(str(nginx), "-s", "reload")
            except BaseException:
                for path, saved_file in saved.items():
                    if saved_file is None:
                        path.unlink(missing_ok=True)
                    else:
                        shutil.copy2(saved_file, path)
                if previous is None:
                    self.current.unlink(missing_ok=True)
                else:
                    atomic_symlink(self.current, previous)
                try:
                    run("systemctl", "daemon-reload")
                    run("systemctl", "restart" if was_active and previous else "stop", "ai-dashboard.service")
                    if not was_enabled:
                        run("systemctl", "disable", "ai-dashboard.service")
                    run(str(nginx), "-t")
                    run(str(nginx), "-s", "reload")
                except BaseException:
                    raise RuntimeError("发布及自动恢复均失败；现场备份在 " + str(backup))
                raise
            print("已发布 " + sha + "；备份：" + str(backup))

    def rollback(self, sha):
        validate_sha(sha)
        validate_path(self.root, no_space=True)
        if os.geteuid() != 0:
            raise ValueError("必须以 root 运行")
        import fcntl
        with (self.root / "release.lock").open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._rollback_locked(sha)

    def _rollback_locked(self, sha):
        target = self.validate_release(sha, require_ready=True)
        environment = read_environment(self.environment_file)
        previous = self.current.resolve(strict=True)
        backup = self.backup(sha)
        try:
            self.switch(target, environment)
        except BaseException:
            atomic_symlink(self.current, previous)
            run("systemctl", "restart", "ai-dashboard.service")
            raise
        print("代码已回滚到 " + sha + "；数据库保持原状，备份：" + str(backup))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "rollback"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--root", type=Path, default=Path("/opt/ai-dashboard"))
    parser.add_argument("--repo-url")
    parser.add_argument("--python", type=Path)
    parser.add_argument("--site", type=Path)
    parser.add_argument("--include", type=Path)
    parser.add_argument("--site-root", type=Path)
    parser.add_argument("--nginx", type=Path)
    args = parser.parse_args(argv)
    try:
        validate_sha(args.sha)
        manager = Release(args.root)
        if args.action == "deploy":
            if not all((args.repo_url, args.python, args.site, args.include, args.site_root, args.nginx)):
                parser.error("deploy 需要 repo-url、python、site、include、site-root、nginx")
            manager.deploy(args.repo_url, args.sha, args.python, args.site,
                           args.include, args.site_root, args.nginx)
        else:
            manager.rollback(args.sha)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print("发布失败：" + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
