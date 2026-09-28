"""Supervise the dashboard's local reader, writer and frpc processes.

The lock identifies the live supervisor. A stop request names its unique
instance; only that supervisor can stop the child handles it owns.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid


if os.name == "nt":
    import ctypes
    from ctypes import wintypes
    import msvcrt
else:
    import fcntl


STATE_NAME = "service-state.json"
LOCK_NAME = "service.lock"
STOP_NAME = "service-stop.json"
HEARTBEAT_SECONDS = 3
LOG_BYTES = 1_048_576


if os.name == "nt":
    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimit),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL


class ChildJob:
    """Windows job whose close kills only this supervisor's assigned children."""

    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        self.handle = _kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise RuntimeError("Could not create child process job")
        limits = _ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise RuntimeError("Could not configure child process job")

    def assign(self, child):
        if self.handle and not _kernel32.AssignProcessToJobObject(self.handle, child._handle):
            if child.poll() is None:
                raise RuntimeError("Could not assign child to process job")

    def close(self):
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path, data):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_config(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"working_directory", "runtime_directory", "environment", "components"}:
            raise ValueError
        working = Path(data["working_directory"])
        runtime = Path(data["runtime_directory"])
        if not working.is_absolute() or not working.is_dir() or not runtime.is_absolute():
            raise ValueError
        if not runtime.resolve().is_relative_to(working.resolve()):
            raise ValueError
        environment = data["environment"]
        if not isinstance(environment, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", k)
            or not isinstance(v, str) or "\x00" in v for k, v in environment.items()
        ):
            raise ValueError
        for key in ("DASHBOARD_DB_PATH", "DASHBOARD_WEB_DIR", "DASHBOARD_VIEW_USERNAME", "DASHBOARD_VIEW_PASSWORD"):
            if not environment.get(key):
                raise ValueError
        for key in ("DASHBOARD_DB_PATH", "DASHBOARD_WEB_DIR"):
            if not Path(environment[key]).is_absolute():
                raise ValueError
        components = data["components"]
        if not isinstance(components, list) or not components:
            raise ValueError
        names = set()
        for component in components:
            if not isinstance(component, dict) or set(component) != {"name", "command"}:
                raise ValueError
            name, command = component["name"], component["command"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z_0-9-]{0,31}", name) or name in names:
                raise ValueError
            if not isinstance(command, list) or not command or any(
                not isinstance(arg, str) or not arg or "\x00" in arg for arg in command
            ) or not Path(command[0]).is_absolute():
                raise ValueError
            names.add(name)
        return working, runtime, environment, components
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("Invalid configuration") from error


class InstanceLock:
    def __init__(self, path):
        self.path = path
        self.stream = None

    def acquire(self, create=False):
        if not create and not self.path.exists():
            return False
        self.stream = self.path.open("a+b" if create else "r+b")
        self.stream.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            self.close()
            return False

    def close(self):
        if self.stream is not None:
            try:
                self.stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            self.stream.close()
            self.stream = None


def lock_is_held(runtime):
    probe = InstanceLock(runtime / LOCK_NAME)
    if probe.acquire():
        probe.close()
        return False
    return (runtime / LOCK_NAME).exists()


def read_live_state(runtime):
    if not lock_is_held(runtime):
        return None
    try:
        state = json.loads((runtime / STATE_NAME).read_text(encoding="utf-8"))
        if (isinstance(state, dict) and state.get("running") is True
                and isinstance(state.get("instance_id"), str)
                and time.time() - state["heartbeat_unix"] < HEARTBEAT_SECONDS):
            return state
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def write_log(pipe, path):
    backup = path.with_suffix(".log.1")
    try:
        stream = path.open("ab")
        try:
            while chunk := pipe.read(4096):
                if stream.tell() + len(chunk) > LOG_BYTES:
                    stream.close()
                    os.replace(path, backup)
                    stream = path.open("wb")
                stream.write(chunk)
                stream.flush()
        finally:
            stream.close()
    finally:
        pipe.close()


def end_child(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=3)


def supervise(config):
    working, runtime, environment, components = load_config(config)
    runtime.mkdir(parents=True, exist_ok=True)
    lock = InstanceLock(runtime / LOCK_NAME)
    if not lock.acquire(create=True):
        raise RuntimeError("Supervisor already running")
    try:
        job = ChildJob()
    except RuntimeError:
        lock.close()
        raise
    instance_id = uuid.uuid4().hex
    stop_path = runtime / STOP_NAME
    stop_path.unlink(missing_ok=True)
    children = {item["name"]: {
        "definition": item, "process": None, "log_thread": None,
        "restarts": 0, "last_exit_code": None, "last_exit_at": None,
        "next_restart_at": None, "next_attempt": 0.0, "started_at": None,
    } for item in components}
    stopped = False

    def request_stop(*_args):
        nonlocal stopped
        stopped = True

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

    def publish(running):
        state = {
            "running": running, "instance_id": instance_id, "pid": os.getpid(),
            "heartbeat_unix": time.time(), "updated_at": utc_now(),
            "components": [{
                "name": name,
                "pid": data["process"].pid if data["process"] and data["process"].poll() is None else None,
                "restarts": data["restarts"], "last_exit_code": data["last_exit_code"],
                "last_exit_at": data["last_exit_at"], "next_restart_at": data["next_restart_at"],
            } for name, data in children.items()],
        }
        atomic_json(runtime / STATE_NAME, state)

    try:
        while not stopped:
            now = time.monotonic()
            for name, data in children.items():
                child = data["process"]
                if child is not None and child.poll() is not None:
                    data["last_exit_code"] = child.returncode
                    data["last_exit_at"] = time.time()
                    data["restarts"] += 1
                    delay = min(30.0, 0.5 * 2 ** min(data["restarts"] - 1, 6))
                    data["next_attempt"] = now + delay
                    data["next_restart_at"] = data["last_exit_at"] + delay
                    data["process"] = None
                    if data["log_thread"]:
                        data["log_thread"].join(timeout=2)
                        data["log_thread"] = None
                if data["process"] is None and now >= data["next_attempt"]:
                    try:
                        child = subprocess.Popen(
                            data["definition"]["command"], cwd=working,
                            env={**os.environ, **environment}, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            startupinfo=_hidden_startupinfo(), shell=False,
                        )
                        try:
                            job.assign(child)
                        except RuntimeError:
                            end_child(child)
                            raise
                        data["process"] = child
                        data["started_at"] = now
                        data["next_restart_at"] = None
                        data["log_thread"] = threading.Thread(
                            target=write_log, args=(child.stdout, runtime / f"{name}.log"), daemon=True
                        )
                        data["log_thread"].start()
                    except OSError:
                        data["restarts"] += 1
                        delay = min(30.0, 0.5 * 2 ** min(data["restarts"] - 1, 6))
                        data["last_exit_at"] = time.time()
                        data["next_attempt"] = now + delay
                        data["next_restart_at"] = data["last_exit_at"] + delay
            publish(True)
            try:
                request = json.loads(stop_path.read_text(encoding="utf-8"))
                if request.get("instance_id") == instance_id:
                    stopped = True
            except (OSError, ValueError, TypeError):
                pass
            time.sleep(0.1)
    finally:
        for data in children.values():
            end_child(data["process"])
            if data["log_thread"]:
                data["log_thread"].join(timeout=2)
        publish(False)
        stop_path.unlink(missing_ok=True)
        job.close()
        lock.close()


def _hidden_startupinfo():
    if os.name != "nt":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return info


def main():
    parser = argparse.ArgumentParser(description="Local dashboard service supervisor")
    parser.add_argument("action", choices=("run", "status", "stop"))
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        _working, runtime, _environment, _components = load_config(args.config)
        if args.action == "run":
            supervise(args.config)
            return 0
        state = read_live_state(runtime)
        if args.action == "status":
            print(json.dumps(state if state is not None else {"running": False}, ensure_ascii=False))
            return 0
        if state is None:
            raise RuntimeError("No live supervisor")
        atomic_json(runtime / STOP_NAME, {"instance_id": state["instance_id"]})
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if not lock_is_held(runtime):
                print(json.dumps({"stopped": True}))
                return 0
            time.sleep(0.1)
        raise RuntimeError("Supervisor did not stop in time")
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
