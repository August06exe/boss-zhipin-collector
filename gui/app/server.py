import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
for _p in (_HERE, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.controller import Controller
from app.engine import EngineRunner
from app.flask_app import create_app
from app.portpick import pick_free_port
from app.settings import SettingsStore, default_data_dir
from app.singleinstance import (acquire, read_global, read_runtime,
                                write_global, write_runtime)

# 这些状态下旧实例有事情在做（采集中/等登录），新副本不打断，只打开它的界面
BUSY_STATES = {"checking", "login_required", "running", "stopping"}


def _probe_state(rt):
    """探测一个已登记实例的健康度和状态；不可达返回 None。"""
    if not rt:
        return None
    try:
        import urllib.request
        url = f"http://127.0.0.1:{rt['port']}/api/state?t={rt['token']}"
        with urllib.request.urlopen(url, timeout=2) as r:
            return json.loads(r.read().decode("utf-8")).get("state")
    except Exception:
        return None


def _kill_pid(pid):
    """结束旧实例进程，让新副本接管。失败返回 False，调用方自行兜底。"""
    if not pid:
        return False
    try:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, int(pid))
        if not handle:
            return False
        ok = bool(ctypes.windll.kernel32.TerminateProcess(handle, 0))
        ctypes.windll.kernel32.CloseHandle(handle)
        return ok
    except Exception:
        return False


# 专属指纹：产品锁名，只出现在本程序的源码与命令行里
OWNED_MARKER = "boss-gui-collector"


def _extract_server_path(cmdline):
    """从命令行里提取 server.py 的路径（带引号/带空格的路径都能认）。"""
    m = re.search(r'"([^"]*server\.py)"', cmdline)
    if m:
        return m.group(1)
    for token in cmdline.split():
        if token.endswith("server.py"):
            return token.strip('"')
    return None


def _looks_ours(pid, cmdline, own):
    """验指纹：这个进程是不是我们自己的服务。

    PID 会被系统回收复用，绝不能看到进程号就直接杀。两级核验：
    1. 新版进程：启动时带 --owned-by=boss-gui-collector 专属参数；
    2. 旧版残留：读它命令行里的 server.py 文件，源码含产品锁名。
    核验不过一律不动手，宁可不接管也不能误杀别人的进程。
    """
    if pid == own or not cmdline:
        return False
    if "python" not in cmdline.lower() or "server.py" not in cmdline:
        return False
    if "--owned-by=" + OWNED_MARKER in cmdline:
        return True
    path = _extract_server_path(cmdline)
    if not path:
        return False
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return OWNED_MARKER in f.read(16384)
    except OSError:
        return False


def _list_python_processes():
    """列出全机器的 python 进程：[(pid, 命令行)]。命令行取不到为空串。"""
    script = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
              "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, timeout=15)
    except Exception:
        return []
    raw = out.stdout or b""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    entries = []
    for line in text.splitlines():
        pid_s, sep, cmdline = line.partition("|")
        if not sep:
            continue
        try:
            entries.append((int(pid_s.strip()), cmdline.strip()))
        except ValueError:
            continue
    return entries


def _pid_looks_ours(pid):
    """按进程号验指纹（接管登记实例前调用）。"""
    for cand_pid, cmdline in _list_python_processes():
        if cand_pid == pid:
            return _looks_ours(pid, cmdline, os.getpid())
    return False


def _sweep_orphan_servers():
    """清扫旧版本残留的孤儿服务进程。

    v1.2.2 之前启动的实例不写全局登记，接管逻辑找不到它们。按
    文件内容指纹认出它们（读 server.py 源码验产品锁名），结束掉
    释放锁；核验不过的进程一个都不碰。
    """
    own = os.getpid()
    killed = []
    for pid, cmdline in _list_python_processes():
        if _looks_ours(pid, cmdline, own) and _kill_pid(pid):
            killed.append(pid)
    return killed


def main():
    lock = acquire("boss-gui-collector")
    if lock is None:
        # 已有实例持锁。分三种情况：正在工作→打开它的界面；空闲→接管；
        # 登记缺失（老版本残留/写入失败）→提示后退出
        print("检测到程序已在运行，检查它的状态...")
        global_rt = read_global()
        state = _probe_state(global_rt)
        if state is None:
            time.sleep(1.5)
            global_rt = read_global()
            state = _probe_state(global_rt)
        if state is not None:
            if state in BUSY_STATES:
                print(f"已有实例正在工作（{state}），直接打开它的界面，不打断采集")
                webbrowser.open(
                    f"http://127.0.0.1:{global_rt['port']}/?t={global_rt['token']}")
                return
            print(f"已有实例空闲（{state}），本副本接管：先结束旧实例")
            old_pid = global_rt.get("pid")
            try:
                looks_ours = _pid_looks_ours(old_pid)
            except Exception:
                looks_ours = False
            if not looks_ours:
                print("旧实例进程指纹不符（可能是进程号已被系统复用），"
                      "为安全起见不强行结束，直接打开它的界面")
                webbrowser.open(
                    f"http://127.0.0.1:{global_rt['port']}/?t={global_rt['token']}")
                return
            _kill_pid(old_pid)
            for _ in range(10):
                lock = acquire("boss-gui-collector")
                if lock is not None:
                    break
                time.sleep(0.5)
            if lock is None:
                print("旧实例未能结束，改为直接打开它的界面")
                webbrowser.open(
                    f"http://127.0.0.1:{global_rt['port']}/?t={global_rt['token']}")
                return
        # 全局登记缺失：多半是旧版本残留的孤儿服务。按特征找到并结束
        # 它们，锁释放后本副本接管
        print("锁被占用但没有登记信息，尝试清理旧版本残留的服务...")
        killed = _sweep_orphan_servers()
        if killed:
            print(f"已结束残留服务进程 {killed}，等待锁释放...")
            time.sleep(1.5)
            for _ in range(10):
                lock = acquire("boss-gui-collector")
                if lock is not None:
                    print("残留实例已清理，本副本接管服务")
                    break
                time.sleep(0.5)
        if lock is None:
            print("锁仍被占用且无法定位持有者，退出。请重启电脑后再试，"
                  "或把启动日志发给作者")
            return
    settings = SettingsStore(default_data_dir())
    stored = settings.load()
    if stored["data_dir"] and stored["data_dir"] != settings.data_dir:
        import shutil
        old_path = settings.path
        new_path = os.path.join(stored["data_dir"], "settings.json")
        settings.set_data_dir(stored["data_dir"])
        # 设置跟数据目录走：新目录还没有设置文件时，把旧的一份搬过来，用户选择不丢
        if not os.path.isfile(new_path) and os.path.isfile(old_path):
            try:
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.copy2(old_path, new_path)
            except OSError:
                pass
        stored = settings.load()
    # Web 界面与 CDP 调试端口各自独立探测，起点错开：干净机器上两者互不抢占
    port = pick_free_port(8600)
    cdp_port = pick_free_port(9222)
    token = secrets.token_urlsafe(16)
    controller = Controller(settings, EngineRunner(), cdp_port=cdp_port)
    app = create_app(controller, settings, token)
    write_runtime(os.path.dirname(os.path.abspath(__file__)), port, token)
    # 机器级登记：多副本场景，后来者靠它找到正在运行的实例（端口/令牌/进程号）
    write_global({"port": port, "token": token, "pid": os.getpid(),
                  "root": _PARENT})
    threading.Timer(1.5, lambda: webbrowser.open(
        f"http://127.0.0.1:{port}/?t={token}")).start()
    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
