import json
import os

RUNTIME_FILENAME = "runtime.json"


def _lock_dir() -> str:
    return os.environ.get("SINGLEINSTANCE_DIR") or os.path.join(
        os.path.expanduser("~"), ".boss-gui")


def acquire(name: str):
    """跨平台单实例锁。Windows 用互斥体，其他平台用 O_EXCL 锁文件。返回锁句柄或 None。"""
    if os.name == "nt":
        import ctypes
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        if ctypes.windll.kernel32.GetLastError() == 183:
            # 已存在：CreateMutexW 依然返回有效句柄，必须关掉。
            # 否则本进程会一直撑着这把锁，接管逻辑永远拿不到它
            ctypes.windll.kernel32.CloseHandle(mutex)
            return None
        return mutex
    os.makedirs(_lock_dir(), exist_ok=True)
    try:
        fd = os.open(os.path.join(_lock_dir(), name + ".lock"),
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return None


def release(lock, name: str) -> None:
    if lock is None:
        return
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.CloseHandle(lock)
        return
    try:
        os.remove(os.path.join(_lock_dir(), name + ".lock"))
    except OSError:
        pass


def runtime_file(gui_dir: str) -> str:
    return os.path.join(gui_dir, RUNTIME_FILENAME)


def write_runtime(gui_dir: str, port: int, token: str) -> None:
    with open(runtime_file(gui_dir), "w", encoding="utf-8") as f:
        json.dump({"port": port, "token": token}, f)


def read_runtime(gui_dir: str):
    try:
        with open(runtime_file(gui_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def global_dir() -> str:
    """机器级共享登记目录：多副本场景下，第二份能找到第一份的端口和令牌。"""
    base = os.environ.get("BOSS_GUI_GLOBAL_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "boss-gui-collector")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    return base


def write_global(payload: dict) -> None:
    try:
        with open(os.path.join(global_dir(), RUNTIME_FILENAME), "w",
                  encoding="utf-8") as f:
            json.dump(payload, f)
    except OSError:
        pass


def read_global():
    try:
        with open(os.path.join(global_dir(), RUNTIME_FILENAME), "r",
                  encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
