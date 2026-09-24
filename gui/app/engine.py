import os
import subprocess
import sys
import threading
import time

from app import winjob

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_GUI_DIR = os.path.dirname(_APP_DIR)
_REPO_DIR = os.path.dirname(_GUI_DIR)

if os.path.isdir(os.path.join(_REPO_DIR, "scripts")):
    ENGINE_CANDIDATE = os.path.join(_REPO_DIR, "scripts", "boss_cdp_raw.py")
else:
    ENGINE_CANDIDATE = os.path.join(_GUI_DIR, "engine", "boss_cdp_raw.py")


def find_engine_script() -> str:
    return ENGINE_CANDIDATE


def _engine_module():
    script_dir = os.path.dirname(find_engine_script())
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import boss_cdp_raw
    return boss_cdp_raw


def label_to_code(name, mapping):
    if not name or name == "不限":
        return None
    return mapping.get(name)


class EngineResult:
    def __init__(self, exit_code=None, lines=None, timed_out=False, killed=False):
        self.exit_code = exit_code
        self.lines = lines or []
        self.timed_out = timed_out
        self.killed = killed


class EngineRunner:
    def __init__(self, python_exe: str = sys.executable, engine_path: str = None):
        self.python_exe = python_exe
        self.engine_path = engine_path or find_engine_script()
        self._current = None
        self._lock = threading.Lock()

    def run(self, args, on_line=None, timeout=None, raw=False,
            job=True) -> EngineResult:
        # -u：子进程 stdout 无缓冲，进度行实时到达（否则管道下子进程按块缓冲，界面日志卡死）
        cmd = [self.python_exe, "-X", "utf8", "-u"]
        if not raw:
            cmd.append(self.engine_path)
        cmd += [str(a) for a in args]
        with self._lock:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1)
            # job=False 用于会拉起专用浏览器的运行：浏览器必须比本程序
            # 活得久（登录态在里面），绝不能进 KILL_ON_JOB_CLOSE 沙箱，
            # 否则 GUI 一退出/被接管结束，浏览器全家陪葬
            if job:
                winjob.assign_child(proc.pid)
            self._current = proc

        lines = []
        err = []
        self._killed = False

        def _pump():
            try:
                for line in proc.stdout:
                    lines.append(line.rstrip("\n"))
                    if on_line:
                        try:
                            on_line(lines[-1])
                        except Exception:
                            pass
            except Exception as e:  # pragma: no cover - 管道异常兜底
                err.append(e)

        pump = threading.Thread(target=_pump, daemon=True)
        pump.start()
        timed_out = False
        deadline = time.time() + timeout if timeout else None
        while proc.poll() is None:
            if deadline and time.time() > deadline:
                timed_out = True
                self._killed = True
                proc.kill()
                break
            time.sleep(0.05)
        code = proc.wait()
        pump.join(timeout=5)
        with self._lock:
            self._current = None
        return EngineResult(code, lines, timed_out=timed_out,
                            killed=timed_out or self._killed)

    def kill_current(self) -> None:
        self._killed = True
        with self._lock:
            proc = self._current
        if proc and proc.poll() is None:
            proc.kill()


def build_scrape_args(port, keyword, city, pages, output, detail_output, filters):
    eng = _engine_module()
    args = ["--keyword", keyword, "--city", city,
            "--pages", max(1, min(int(pages), 10)),
            "--format", "json",
            "--output", output, "--detail-output", detail_output,
            "--cdp-port", port]
    code = label_to_code(filters.get("salary"), eng.SALARY_MAP)
    if code:
        args += ["--salary", code]
    code = label_to_code(filters.get("experience"), eng.EXPERIENCE_MAP)
    if code:
        args += ["--experience", code]
    code = label_to_code(filters.get("degree"), eng.DEGREE_MAP)
    if code:
        args += ["--degree", code]
    code = label_to_code(filters.get("scale"), eng.SCALE_MAP)
    if code:
        args += ["--scale", code]
    return args


def build_check_args(port):
    return ["--check", "--cdp-port", port]


def build_setup_args(browser, port, wait_login=False):
    """拉起专用浏览器。wait_login=True 时打开登录页并等待扫码完成
    （引擎默认等 300 秒，期间登录页保持打开）；False 保持旧行为。"""
    flag = "--setup-edge" if browser == "edge" else "--setup-chrome"
    args = [flag, "--cdp-port", port]
    if not wait_login:
        args.append("--no-wait-login")
    return args


def build_stop_args(browser):
    return ["--stop-edge" if browser == "edge" else "--stop-chrome"]


def classify_check(lines, exit_code):
    text = "\n".join(lines)
    # "未登录" 与 "未检测到可用登录态" 是同一结论的两种历史措辞
    if "未登录" in text or "未检测到可用登录态" in text:
        return "not_logged_in"
    if "环境存在异常" in text or "已被限制" in text or "访问频繁" in text:
        return "restricted"
    if "CDP" in text and ("不通" in text or "无法连接" in text or "未启动" in text):
        return "cdp_down"
    if "依赖" in text and ("缺失" in text or "不可导入" in text):
        return "deps_missing"
    if exit_code == 0 and ("全部通过" in text or "✅" in text):
        return "ok"
    return "unknown"
