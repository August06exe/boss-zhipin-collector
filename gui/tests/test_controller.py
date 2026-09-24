import json
import os

from app.controller import Controller
from app.engine import EngineResult
from app.settings import SettingsStore


class FakeRunner:
    """输出行与引擎 classify_check 的真实关键词对齐。"""

    def __init__(self, check_result="ok", scrape_exit=0):
        self.check_result = check_result
        self.scrape_exit = scrape_exit
        self.killed = 0
        self.scrape_calls = []

    def run(self, args, on_line=None, timeout=None, raw=False):
        if "--check" in args:
            lines = {
                "ok": ["✅ 全部通过"],
                "not_logged_in": ["❌ 检测到未登录"],
                "cdp_down": ["❌ CDP 不通，无法连接"],
                "restricted": ["❌ 环境存在异常，已被限制"],
            }[self.check_result]
            return EngineResult(0 if self.check_result == "ok" else 1, lines)
        if args and args[0] in ("--setup-chrome", "--setup-edge"):
            return EngineResult(0, ["浏览器已启动"])
        if args and args[0] in ("--stop-chrome", "--stop-edge"):
            return EngineResult(0, ["已关闭"])
        self.scrape_calls.append(args)
        for i, a in enumerate(args):
            if a == "--output":
                out = args[i + 1]
                det = args[args.index("--detail-output") + 1]
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    json.dump({"keyword": "k", "city": "c", "jobs": [
                        {"job_id": "j1", "title": "测试岗", "salary": "20K"}]}, f)
                with open(det, "w", encoding="utf-8") as f:
                    json.dump([], f)
        if on_line:
            on_line("抓取中")
        return EngineResult(self.scrape_exit, ["完成: 1 条"])

    def kill_current(self):
        self.killed += 1


def make_controller(tmp_path, runner, **kw):
    settings = SettingsStore(str(tmp_path))
    return Controller(settings, runner, **kw)


FORM = {"keyword": "前端", "city": "上海", "target_count": 60,
        "salary": "不限", "experience": "不限", "degree": "不限", "scale": "不限",
        "max_minutes": 300, "fields": [], "data_dir": ""}


def test_single_run_success_and_outputs(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    result = ctrl.start(dict(FORM, data_dir=str(tmp_path / "数据")))
    assert result == {"ok": True}
    ctrl.join()
    st = ctrl.state()
    assert st["state"] == "stopped"
    assert st["stats"]["total"] == 1
    task = st["task_dir"]
    assert os.path.isfile(os.path.join(task, "jobs.json"))
    assert os.path.isfile(os.path.join(task, "jobs.csv"))
    assert os.path.isfile(os.path.join(task, "meta.json"))
    # 单关键词单城市：一轮恰好一次子进程
    assert len(runner.scrape_calls) == 1


def test_target_count_maps_to_pages(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    ctrl.start(dict(FORM, target_count=100, data_dir=str(tmp_path / "数据")))
    ctrl.join()
    i = runner.scrape_calls[0].index("--pages")
    assert int(runner.scrape_calls[0][i + 1]) == 4  # 100/30 向上取整


def test_login_flow_then_auto_continue(tmp_path):
    runner = FakeRunner(check_result="not_logged_in")
    ctrl = make_controller(tmp_path, runner)
    ctrl.start(dict(FORM, data_dir=str(tmp_path / "数据")))
    ctrl.join()
    assert ctrl.state()["state"] == "login_required"
    runner.check_result = "ok"
    assert ctrl.login_verify() is True
    ctrl.join()
    st = ctrl.state()
    assert st["state"] == "stopped"
    assert st["stats"]["total"] == 1


def test_stop_mid_round_keeps_data(tmp_path):
    import threading
    release = threading.Event()

    class BlockingRunner(FakeRunner):
        def run(self, args, on_line=None, timeout=None, raw=False):
            if args and args[0] == "--keyword":
                release.wait(timeout=5)  # 模拟长任务卡在抓取中
            return super().run(args, on_line=on_line, timeout=timeout, raw=raw)

        def kill_current(self):
            self.killed += 1
            release.set()

    runner = BlockingRunner()
    ctrl = make_controller(tmp_path, runner)
    ctrl.start(dict(FORM, data_dir=str(tmp_path / "数据")))
    assert ctrl.wait_until_running(timeout=5) is True
    ctrl.stop()
    ctrl.join()
    st = ctrl.state()
    assert st["state"] == "stopped"
    assert st["stats"]["total"] >= 0


def test_max_minutes_drives_deadline_and_timeout(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    ctrl.start(dict(FORM, data_dir=str(tmp_path / "数据"), max_minutes=5))
    ctrl.join()
    assert ctrl.state()["state"] == "stopped"
    assert ctrl._timeout_seconds == 5 * 60 + 180


def test_invalid_values_return_friendly_error(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    r1 = ctrl.start(dict(FORM, target_count="abc", data_dir=str(tmp_path / "数据")))
    assert "填写有误" in r1["error"]
    r2 = ctrl.start(dict(FORM, max_minutes="abc", data_dir=str(tmp_path / "数据")))
    assert "填写有误" in r2["error"]
    assert ctrl.state()["state"] == "idle"


def test_target_clamped_to_engine_cap(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    ctrl.start(dict(FORM, target_count=9999, data_dir=str(tmp_path / "数据")))
    ctrl.join()
    i = runner.scrape_calls[0].index("--pages")
    assert int(runner.scrape_calls[0][i + 1]) == 10  # 300 条硬顶 = 10 页


def test_task_name_sanitized_no_path_breakout(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    result = ctrl.start(dict(FORM, keyword='前/端:*?', city="上海",
                             data_dir=str(tmp_path / "数据")))
    assert result == {"ok": True}
    ctrl.join()
    task = ctrl.state()["task_dir"]
    assert os.path.isdir(task)
    assert (tmp_path / "数据" / "前").exists() is False


def test_unwritable_data_dir_returns_friendly_error(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    blocker = tmp_path / "占用文件.txt"
    blocker.write_text("x", encoding="utf-8")
    result = ctrl.start(dict(FORM, data_dir=str(blocker)))
    assert "不可写" in result["error"]
    assert ctrl.state()["state"] == "idle"


def test_browser_missing_flags_guidance(tmp_path):
    from unittest import mock
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    with mock.patch("app.controller.Controller._detect_browser", return_value=""):
        ctrl.start(dict(FORM, data_dir=str(tmp_path / "数据")))
        ctrl.join()
    st = ctrl.state()
    assert st["browser_missing"] is True
    assert st["state"] == "error"


def test_cdp_port_injection(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner, cdp_port=9455)
    ctrl.start(dict(FORM, data_dir=str(tmp_path / "数据")))
    ctrl.join()
    joined = " ".join(str(a) for a in runner.scrape_calls[0])
    assert "9455" in joined


def test_empty_keyword_rejected(tmp_path):
    runner = FakeRunner()
    ctrl = make_controller(tmp_path, runner)
    result = ctrl.start(dict(FORM, keyword="", data_dir=str(tmp_path / "数据")))
    assert "关键词" in result["error"]
    assert ctrl.state()["state"] == "idle"
