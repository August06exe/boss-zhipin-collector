import json
import os
import subprocess
import sys
import time


def root_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_runtime(root):
    """runtime.json 的会合点：包根目录优先，其次 app/（server 同目录）。"""
    for path in (os.path.join(root, "runtime.json"),
                 os.path.join(root, "app", "runtime.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return None


def _alive(port, token):
    """runtime.json 可能是上次会话的残留，探活通过才算数。"""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/state?t={token}")
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ctypes_msg(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "BOSS职位采集器", 0)
    except Exception:
        print(text)


def log_write(log, log_path, text):
    """launcher 自己的日志行每次独立追加打开。

    长跑的服务持有从 launcher 继承的旧句柄，写文件时用的是自己的
    偏移量；launcher 若复用同一个句柄对象，两边的偏移会互相覆盖。
    每次以追加模式重新打开（O_APPEND 到末尾），行与行就不会踩踏。
    """
    try:
        log.write(text)
        log.flush()
    except OSError:
        try:
            with open(log_path, "a", encoding="utf-8", buffering=1) as f:
                f.write(text)
        except OSError:
            pass


def read_global():
    """机器级共享登记：另一份副本接管服务后，登记写到全局位置。"""
    base = os.environ.get("BOSS_GUI_GLOBAL_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "boss-gui-collector")
    try:
        with open(os.path.join(base, "runtime.json"), "r",
                  encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def main():
    root = root_dir()
    python = os.path.join(root, "runtime", "python.exe")
    server = os.path.join(root, "app", "server.py")
    if not (os.path.isfile(python) and os.path.isfile(server)):
        ctypes_msg("找不到运行文件，请确认解压完整后再试")
        return

    # 服务输出全部落到包根的启动日志，出问题有据可查
    log_path = os.path.join(root, "启动日志.txt")
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    log_write(log, log_path, f"\n===== 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    try:
        # -u：无缓冲输出。子进程被外部（如杀毒软件）结束时，
        # 块缓冲里的内容会整体丢失，日志必须逐行落盘才有排查价值
        proc = subprocess.Popen([python, "-X", "utf8", "-u", server,
                                "--owned-by=boss-gui-collector"], cwd=root,
                                stdout=log, stderr=subprocess.STDOUT,
                                creationflags=0x08000000)  # CREATE_NO_WINDOW
    except OSError as e:
        log_write(log, log_path, f"无法启动内置引擎：{e}\n")
        log.close()
        ctypes_msg(
            "无法启动内置引擎，多数是杀毒软件拦住了它。\n\n"
            "请把整个程序文件夹加入杀毒软件白名单后再试；\n"
            f"详细原因已写入：{log_path}")
        return
    log_write(log, log_path, f"内置引擎已启动（进程号 {proc.pid}），等待服务就绪...\n")

    # 等服务就绪：最多 90 秒（杀软首扫可能拖慢第一次启动）；
    # 服务进程提前退出就不干等，直接报错并把退出码写进日志
    for waited in range(90):
        if proc.poll() is not None:
            # 服务退出了。最常见原因：程序已在运行，新实例要么打开了已有
            # 界面、要么已接管服务。先在两处登记里找健康实例，再报错
            for _ in range(15):
                for cand in (read_runtime(root), read_global()):
                    if cand and _alive(cand["port"], cand["token"]):
                        log_write(log, log_path,
                                  "服务进程退出，但已有健康实例在运行，界面由它自行打开\n")
                        return
                time.sleep(1)
            code = proc.returncode
            log_write(log, log_path, f"服务进程提前退出，退出码 {code}，且没有可用的已运行实例\n")
            log.close()
            ctypes_msg(
                "服务启动失败，程序提前退出了（退出码 "
                f"{code}）。\n\n详细原因已写进这个文件，把它发给作者即可排查：\n{log_path}")
            return
        if waited and waited % 10 == 0:
            log_write(log, log_path, f"仍在等待服务就绪（第 {waited} 秒）...\n")
        rt = read_runtime(root)
        if rt and _alive(rt["port"], rt["token"]):
            log_write(log, log_path, "服务就绪，界面由服务自动打开，本启动器退出\n")
            return
        # 本副本迟迟没就绪、但全局登记里有个健康实例：说明服务正由
        # 另一份副本提供（可能是接管，可能是加入）。界面会自动打开，
        # 本启动器使命结束，静默退出
        g = read_global()
        if g and _alive(g["port"], g["token"]):
            log_write(log, log_path, "服务正由已运行的实例提供，界面将自动打开，本启动器退出\n")
            log.close()
            return
        time.sleep(1)
    log_write(log, log_path, "等待 90 秒仍未就绪，放弃。进程存活说明服务卡住，"
              "多数是杀毒软件实时扫描在反复拦截\n")
    log.close()
    ctypes_msg(
        "服务启动超时（90 秒没就绪）。\n\n"
        "多数是杀毒软件拦住了内置浏览器引擎，可以：\n"
        "1. 把整个程序文件夹加入杀毒软件白名单，再双击一次\n"
        "2. 把文件夹挪到桌面再试\n"
        f"3. 还不行就把这个文件发给作者：{log_path}")


if __name__ == "__main__":
    main()
