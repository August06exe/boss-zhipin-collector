import os
import re
import threading
from datetime import datetime

from app.engine import (build_check_args, build_scrape_args, build_setup_args,
                        build_stop_args, classify_check)
from app.export import (archive_round, build_meta, export_task, load_master,
                        load_upstream_results, save_master, task_dir)
from app.merge import merge_into

LOG_LIMIT = 500


def parse_detail_progress(line):
    """从引擎输出行解析详情抓取进度，如 "[3/60] 某公司 - 某岗位"。

    列表阶段和详情阶段都有方括号进度；详情阶段的行数格式固定如此。
    返回 {"done": int, "total": int} 或 None。
    """
    m = re.search(r"\[(\d+)/(\d+)\]", line or "")
    if not m:
        return None
    try:
        done, total = int(m.group(1)), int(m.group(2))
    except ValueError:
        return None
    if total <= 0 or done > total:
        return None
    return {"done": done, "total": total}



class Controller:
    def __init__(self, settings, runner, clock=None, sleep=None, cdp_port=9222):
        import time as time_mod
        self.settings = settings
        self.runner = runner
        self._clock = clock or time_mod.time
        self._sleep = sleep or time_mod.sleep
        self._threads = []
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()
        self._state = "idle"
        self._logs = []
        self._stats = {"total": 0, "new": 0, "updated": 0}
        self._details = None
        self._rounds = []
        self._task_dir = ""
        self._task_name = ""
        self._deadline_at = 0
        self._browser = self._detect_browser()
        self._port = cdp_port
        self._form = {}
        self._current = None

    # ---- 对外 API ----
    def start(self, form: dict) -> dict:
        if self._threads_alive():
            return {"error": "已有任务在进行中，请先点击结束"}
        # 手动输入的路径常见三种脏东西：首尾空格、资源管理器复制的引号、~ 开头
        data_dir = str(form.get("data_dir") or "").strip().strip('"').strip()
        if data_dir.startswith("~"):
            data_dir = os.path.expanduser(data_dir)
        if not data_dir:
            data_dir = self.settings.load()["data_dir"]
        if not data_dir:
            from app.settings import default_data_dir
            data_dir = default_data_dir()
        try:
            os.makedirs(data_dir, exist_ok=True)
            probe = os.path.join(data_dir, ".write_test")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
        except OSError:
            return {"error": "数据保存位置不可写，请在首页换一个文件夹"}
        keyword = str(form.get("keyword") or "").strip()
        city = str(form.get("city") or "").strip()
        if not keyword:
            return {"error": "请填写关键词"}
        if not city:
            return {"error": "请选择城市"}
        try:
            target_count = max(10, min(int(form.get("target_count") or 300), 300))
            max_minutes = max(1, min(int(form.get("max_minutes") or 300), 600))
        except (TypeError, ValueError, OverflowError):
            return {"error": "目标条数或最长运行时间填写有误，请检查后重试"}
        pages = max(1, min(-(-target_count // 30), 10))  # 目标换算页数：30 条/页，向上取整
        self._timeout_seconds = max_minutes * 60 + 180  # 时长到点强停，留收尾缓冲
        now = datetime.now().strftime("%Y%m%d_%H%M")
        self._task_name = re.sub(r'[\\/:*?"<>|]', "_", f"{keyword}_{city}_{now}")
        self._task_dir = task_dir(data_dir, self._task_name)
        self._deadline_at = self._clock() + max_minutes * 60
        self._stop_flag.clear()
        valid_fields = set()
        try:
            from app.fields import field_keys
            valid_fields = set(field_keys())
        except ImportError:
            pass
        self._form = dict(form)
        self._form["keyword"] = keyword
        self._form["city"] = city
        self._form["pages"] = pages
        self._form["target_count"] = target_count
        self._form["max_minutes"] = max_minutes
        self._form["fields"] = [k for k in (form.get("fields") or [])
                                if isinstance(k, str) and k in valid_fields]
        self.settings.save(dict(form, data_dir=data_dir))
        self._spawn(self._run_task)
        return {"ok": True}

    def stop(self) -> None:
        self._stop_flag.set()
        with self._lock:
            if self._state == "running":
                self._state = "stopping"
        kill = getattr(self.runner, "kill_current", None)
        if kill:
            kill()

    def login_start_browser(self) -> None:
        browser = self._detect_browser()
        self._browser = browser
        self._log("正在打开 BOSS 登录页：在弹出的专用浏览器里扫码即可"
                  "（最长等 5 分钟，登录成功自动继续）")
        res = self.runner.run(build_setup_args(browser, self._port, wait_login=True),
                              on_line=self._on_line, timeout=420, job=False)
        if res.timed_out or res.killed:
            self._log("等待登录超时被终止。浏览器若还开着，请在里面完成登录后"
                      "点「我登录好了」；若已关闭，重新点「启动专用浏览器」")
        elif res.exit_code != 0:
            tail = "；".join(res.lines[-3:]) if res.lines else "无输出"
            self._log(f"浏览器拉起或登录等待异常退出（退出码 {res.exit_code}）：{tail}")
        else:
            self._log("检测到登录成功，自动继续…")
            self.login_verify()
            return

    def login_verify(self) -> bool:
        self._log("正在检查登录状态...")
        res = self.runner.run(build_check_args(self._port),
                              on_line=self._on_line, timeout=300)
        verdict = classify_check(res.lines, res.exit_code)
        if verdict == "ok":
            self._log("登录确认成功，开始采集")
            self._set("ready")
            self._spawn(self._loop)
            return True
        tail = "；".join(res.lines[-2:]) if res.lines else "无输出"
        self._log(f"还没检测到登录（{verdict}）：{tail}。"
                  "请在专用浏览器里登录 zhipin.com 后再点「我登录好了」")
        return False

    def cleanup_stale_browser(self) -> None:
        browser = self._detect_browser() or "chrome"
        self.runner.run(build_stop_args(browser), timeout=120)
        self._log("已尝试关闭上次遗留的专用浏览器")

    def state(self) -> dict:
        with self._lock:
            return {"state": self._state, "task": self._task_name,
                    "task_dir": self._task_dir, "stats": dict(self._stats),
                    "rounds": list(self._rounds), "logs": list(self._logs)[-200:],
                    "deadline_at": self._deadline_at,
                    "target_count": self._form.get("target_count"),
                    "max_minutes": self._form.get("max_minutes"),
                    "browser": self._browser,
                    "browser_missing": self._browser == "",
                    "current": self._current,
                    "details": dict(self._details) if self._details else None,
                    "scope": {"keyword": self._form.get("keyword", ""),
                              "city": self._form.get("city", ""),
                              "pages": self._form.get("pages", 3)}}

    def join(self, timeout=None):
        """等待控制器派生的全部线程结束（线程会级联 spawn，需循环收割）。"""
        waited = 0.0
        while True:
            alive = [t for t in list(self._threads) if t.is_alive()]
            if not alive:
                break
            for t in alive:
                t.join(timeout if timeout else 0.2)
            if timeout is not None:
                waited += timeout
                if waited >= timeout * len(self._threads) + 1:
                    break

    def wait_until_running(self, timeout=5):
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            with self._lock:
                if self._state == "running":
                    return True
            self._sleep(0.05)
        return False

    # ---- 内部 ----
    def _threads_alive(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def _spawn(self, target) -> None:
        def _wrapped():
            try:
                target()
            except Exception as e:
                self._log(f"内部错误：{type(e).__name__}: {e}")
                self._set("error")
        t = threading.Thread(target=_wrapped, daemon=True)
        self._threads.append(t)
        t.start()

    def _log(self, msg: str) -> None:
        line = datetime.now().strftime("%H:%M:%S ") + msg
        with self._lock:
            self._logs.append(line)
            del self._logs[:-LOG_LIMIT]
        # 同步落到 启动日志.txt（服务 stdout 被启动器重定向到该文件），
        # 用户把这一个文件发来即可远程定位问题
        try:
            print(line, flush=True)
        except OSError:
            pass

    def _set(self, s: str) -> None:
        with self._lock:
            self._state = s

    def _detect_browser(self) -> str:
        try:
            from app.engine import _engine_module
            eng = _engine_module()
            if os.path.isfile(eng.get_default_chrome_path()):
                return "chrome"
            if os.path.isfile(eng.get_default_edge_path()):
                return "edge"
        except (ImportError, OSError):
            pass
        return ""

    def _run_task(self) -> None:
        self._browser = self._detect_browser()
        if not self._browser:
            self._set("error")
            self._log("没有检测到 Chrome 或 Edge：请先安装其中一款浏览器再来")
            return
        self._set("checking")
        self._log("正在检查浏览器与登录状态…")
        res = self.runner.run(build_check_args(self._port),
                              on_line=self._on_line, timeout=300)
        verdict = classify_check(res.lines, res.exit_code)
        if verdict == "cdp_down":
            # 先切到登录向导再进入等待：5 分钟的扫码窗口里界面必须有指引，
            # 不能停在「检查中」让用户以为卡死（真机首跑实测踩坑）
            self._set("login_required")
            self._log("已打开 BOSS 登录页：请在弹出的专用浏览器里扫码登录"
                      "（最长等 5 分钟，登录成功自动开始采集）")
            setup = self.runner.run(
                build_setup_args(self._browser, self._port, wait_login=True),
                on_line=self._on_line, timeout=420, job=False)
            if setup.timed_out or setup.killed:
                self._log("等待登录超时。浏览器若还开着，请在里面完成登录后"
                          "点「我登录好了」；若已关闭，重新点「开始采集」")
                self._set("error")
                return
            res = self.runner.run(build_check_args(self._port),
                                  on_line=self._on_line, timeout=300)
            verdict = classify_check(res.lines, res.exit_code)
        if verdict == "not_logged_in":
            self._set("login_required")
            self._log("需要登录：请按向导在专用浏览器中登录 BOSS直聘")
            return
        if verdict == "restricted":
            self._set("error")
            self._log("账号或网络环境被暂时限制，建议 1 小时后再试")
            return
        if verdict != "ok":
            self._set("error")
            self._log("环境检查未通过，请重试或联系作者")
            return
        self._set("ready")
        self._spawn(self._loop)

    def _on_line(self, line: str) -> None:
        self._log(line)
        prog = parse_detail_progress(line)
        if prog:
            with self._lock:
                self._details = prog

    def _loop(self) -> None:
        self._set("running")
        with self._lock:
            self._details = None
        form = self._form
        master = load_master(self._task_dir)
        with self._lock:
            self._current = {"keyword": form["keyword"], "city": form["city"],
                             "pair": 1, "pair_total": 1}
        self._log(f"目标 {form['target_count']} 条（约 {form['pages']} 页），"
                  f"最长运行 {form['max_minutes']} 分钟…")
        tag = re.sub(r'[\/:*?"<>|]', "_", f"{form['keyword']}_{form['city']}")
        list_out = os.path.join(self._task_dir, "raw", f"up_list_{tag}.json")
        det_out = os.path.join(self._task_dir, "raw", f"up_details_{tag}.json")
        args = build_scrape_args(
            self._port, form["keyword"], form["city"], form["pages"],
            list_out, det_out,
            {k: form.get(k, "不限") for k in
             ("salary", "experience", "degree", "scale")})
        res = self.runner.run(args, on_line=self._on_line,
                              timeout=self._timeout_seconds)
        if res.timed_out or res.killed:
            self._log("已到最长运行时间或手动停止，已抓到的部分照常保留")
            det = self._details
            if det and det["done"] < det["total"]:
                self._log(f"职位描述只抓到 {det['done']}/{det['total']}："
                          "重跑同一关键词和城市会自动去重补全，不会产生重复数据")
            elif det is None:
                self._log("职位描述（JD）还没开始抓：重跑同一关键词和城市即可补全")
        elif res.exit_code != 0:
            self._log("这一批没抓到数据（网络或环境异常），已保留之前的数据")
        with self._lock:
            self._current = None
        try:
            jobs, details, load_err = load_upstream_results(list_out, det_out)
            if load_err:
                raise ValueError(load_err)
            for job in jobs:
                d = details.get(str(job.get("job_id")), {})
                jd = d.get("job_description") or d.get("description") or ""
                if jd:
                    job["job_description"] = jd
            stats = merge_into(master, jobs,
                               datetime.now().isoformat(timespec="seconds"))
            self._stats = {"total": stats["total"], "new": stats["new"],
                           "updated": stats["updated"]}
            save_master(self._task_dir, master)
            archive_round(self._task_dir, 1, jobs)
            export_task(self._task_dir, form.get("fields") or [],
                        build_meta(self._task_name, form,
                                   [{"round": 1, **stats}], master))
            self._rounds = [{"round": 1, **stats}]
            self._log(f"完成：新增 {stats['new']}，共 {stats['total']} 条")
        except (OSError, ValueError, AttributeError):
            self._log("数据写入或读取失败（磁盘、权限或文件异常），已保留之前的数据")
        try:
            export_task(self._task_dir, self._form.get("fields") or [],
                        build_meta(self._task_name, self._form, self._rounds, master))
        except OSError:
            self._log("收尾导出失败（磁盘或权限问题），原始数据仍在 raw/ 中")
        self._log(f"已结束：共 {len(master)} 条数据保存在 {self._task_dir}")
        self._set("stopped")
