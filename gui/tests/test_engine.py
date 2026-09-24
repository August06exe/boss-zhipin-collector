import sys

from app.engine import (EngineRunner, build_scrape_args, classify_check,
                        find_engine_script, label_to_code)


def test_find_engine_script_exists():
    import os
    assert os.path.isfile(find_engine_script())


def test_label_to_code():
    import boss_cdp_raw
    assert label_to_code("10-20K", boss_cdp_raw.SALARY_MAP) == "405"
    assert label_to_code("不限", boss_cdp_raw.SALARY_MAP) is None
    assert label_to_code("乱写的", boss_cdp_raw.SALARY_MAP) is None


def test_build_scrape_args():
    args = build_scrape_args(
        port=9300, keyword="前端", city="上海", pages=3,
        output="o.json", detail_output="d.json",
        filters={"salary": "10-20K", "experience": "不限", "degree": "本科", "scale": "不限"})
    joined = " ".join(str(a) for a in args)
    assert "--keyword" in joined and "前端" in joined
    assert "--salary" in joined and "405" in joined
    assert "--degree" in joined and "203" in joined
    assert "--experience" not in joined
    assert "--scale" not in joined
    assert "--cdp-port" in joined and "9300" in joined
    assert "--pages" in joined and "3" in joined


def test_pages_clamped_to_ten():
    args = build_scrape_args(
        port=9300, keyword="前端", city="上海", pages=99,
        output="o.json", detail_output="d.json", filters={})
    i = args.index("--pages")
    assert int(args[i + 1]) == 10


def test_classify_check_from_noisy_lines():
    noisy = ["=" * 50, "  BOSS直聘 CDP 环境检查", "⚠️ GBK 兼容行 \ufffd", "",
             "[2/3] CDP 连通性...", "  ❌ CDP 不通，无法连接 9222 端口"]
    assert classify_check(noisy, 1) == "cdp_down"
    assert classify_check(["  ❌ 检测到未登录"], 1) == "not_logged_in"
    # 引擎实际输出的措辞（v1.2.9 用户日志抓到的漏判样本）
    assert classify_check(["❌ 未检测到可用登录态（code: 0）"], 1) == "not_logged_in"
    assert classify_check(["环境存在异常，已被限制"], 1) == "restricted"
    assert classify_check(["依赖缺失 requests"], 1) == "deps_missing"
    assert classify_check(["全部通过"], 0) == "ok"
    assert classify_check(["奇怪的输出"], 1) == "unknown"


def test_run_captures_lines_and_kills_on_timeout():
    runner = EngineRunner(python_exe=sys.executable)
    res = runner.run(["-c", "print('行A'); print('行B')"], raw=True)
    assert res.exit_code == 0
    assert any("行A" in x for x in res.lines)
    slow = EngineRunner(python_exe=sys.executable)
    res2 = slow.run(["-c", "import time; time.sleep(30)"], timeout=1, raw=True)
    assert res2.timed_out is True
    assert res2.killed is True


def test_pages_clamped_low_and_high():
    for raw, expect in ((0, 1), (-5, 1), (99, 10)):
        args = build_scrape_args(
            port=9300, keyword="前端", city="上海", pages=raw,
            output="o.json", detail_output="d.json", filters={})
        i = args.index("--pages")
        assert int(args[i + 1]) == expect


def test_nonzero_exit_is_failure_not_killed():
    runner = EngineRunner(python_exe=sys.executable)
    res = runner.run(["-c", "import sys; sys.exit(2)"], raw=True)
    assert res.exit_code == 2
    assert res.killed is False
    assert res.timed_out is False


def test_browser_launch_run_skips_job(tmp_path, monkeypatch):
    """拉起专用浏览器的运行不得进入 KILL_ON_JOB_CLOSE 沙箱。

    浏览器由引擎子进程拉起、自动继承其作业归属；一旦入沙箱，GUI 退出
    或被接管结束时浏览器全家陪葬（用户表现为"BOSS 页面一闪而过"）。
    """
    import app.engine as eng

    calls = []
    monkeypatch.setattr(eng.winjob, "assign_child",
                        lambda pid: calls.append(pid) or 123)

    r = eng.EngineRunner()

    import sys as _sys
    # job=False：不 assign（用 raw=True 跑一条瞬时命令避免依赖引擎文件）
    res = r.run(["-c", "print('x')"], raw=True, timeout=30, job=False)
    assert res.exit_code == 0
    assert calls == []

    # job=True（默认）：assign 被调用
    res = r.run(["-c", "print('y')"], raw=True, timeout=30)
    assert res.exit_code == 0
    assert len(calls) == 1
