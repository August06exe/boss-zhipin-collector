import json
import os

from app.export import (archive_round, export_task, load_master,
                        load_upstream_results, save_master, task_dir)


def _prep_upstream(tmp_path):
    list_path = tmp_path / "up_list.json"
    detail_path = tmp_path / "up_details.json"
    list_path.write_text(json.dumps({
        "keyword": "前端", "city": "上海", "total": 1,
        "jobs": [{"job_id": "abc", "title": "前端", "boss_name": "公司A"}],
    }, ensure_ascii=False), encoding="utf-8")
    detail_path.write_text(json.dumps(
        [{"job_id": "abc", "job_description": "职责：…"}],
        ensure_ascii=False), encoding="utf-8")
    return str(list_path), str(detail_path)


def test_load_upstream_results_merges_details(tmp_path):
    lp, dp = _prep_upstream(tmp_path)
    jobs, details, err = load_upstream_results(lp, dp)
    assert jobs[0]["job_id"] == "abc"
    assert details["abc"]["job_description"] == "职责：…"
    assert err == ""


def test_task_dir_and_master_roundtrip_chinese(tmp_path):
    tdir = task_dir(str(tmp_path), "前端_上海_20260923_1530")
    assert "前端_上海" in tdir
    save_master(tdir, {"abc": {"job_id": "abc"}})
    assert load_master(tdir)["abc"]["job_id"] == "abc"
    assert os.path.isfile(os.path.join(tdir, "raw", "master.json"))


def test_archive_round(tmp_path):
    tdir = task_dir(str(tmp_path), "任务A")
    archive_round(tdir, 1, [{"job_id": "abc"}])
    p = os.path.join(tdir, "raw", "round_1.json")
    assert json.load(open(p, encoding="utf-8"))[0]["job_id"] == "abc"


def test_export_task_writes_three_files_with_selection(tmp_path):
    tdir = task_dir(str(tmp_path), "任务B")
    save_master(tdir, {"abc": {
        "job_id": "abc", "title": "前端", "boss_name": "公司A",
        "first_seen": "t0", "last_seen": "t1",
    }})
    meta = {"轮次": [{"round": 1, "new": 1}]}
    export_task(tdir, ["title", "company_name"], meta)
    jobs = json.load(open(os.path.join(tdir, "jobs.json"), encoding="utf-8"))
    assert jobs[0] == {"title": "前端", "company_name": "公司A"}
    csv_raw = open(os.path.join(tdir, "jobs.csv"), "rb").read()
    assert csv_raw.startswith(b"\xef\xbb\xbf")
    assert "职位名称".encode("utf-8") in csv_raw
    meta_out = json.load(open(os.path.join(tdir, "meta.json"), encoding="utf-8"))
    assert meta_out["统计"]["总数"] == 1
    assert meta_out["轮次"] == meta["轮次"]


def test_load_upstream_normalizes_jd_key(tmp_path):
    list_path = tmp_path / "l.json"
    detail_path = tmp_path / "d.json"
    list_path.write_text(json.dumps({"jobs": [{"job_id": "x1", "title": "T"}]}, ensure_ascii=False), encoding="utf-8")
    detail_path.write_text(json.dumps([{"job_id": "x1", "jd": "职位描述内容"}], ensure_ascii=False), encoding="utf-8")
    jobs, details, err = load_upstream_results(str(list_path), str(detail_path))
    assert details["x1"]["job_description"] == "职位内容"[:0] + "职位描述内容"


def test_export_survives_unknown_and_none_keys(tmp_path):
    tdir = task_dir(str(tmp_path), "任务None")
    save_master(tdir, {"a": {"job_id": "a", "title": "T"}})
    export_task(tdir, [None, "title", "不存在的键"], {})
    jobs = json.load(open(os.path.join(tdir, "jobs.json"), encoding="utf-8"))
    assert jobs == [{"title": "T"}]


def test_bom_and_gbk_list_files_do_not_crash(tmp_path):
    list_bom = tmp_path / "bom.json"
    list_bom.write_bytes(b"\xef\xbb\xbf" + json.dumps({"jobs": []}).encode("utf-8"))
    jobs, details, err = load_upstream_results(str(list_bom), str(tmp_path / "nope.json"))
    assert jobs == []
    list_gbk = tmp_path / "gbk.json"
    list_gbk.write_bytes(b'{"jobs": [{"job_id": "\xc9\xf1"}]}')
    jobs2, _d, err2 = load_upstream_results(str(list_gbk), str(tmp_path / "nope.json"))
    assert jobs2 == [] and "损坏" in err2


def test_load_upstream_surfaces_corrupt_file_error(tmp_path):
    bad = tmp_path / "bad_list.json"
    bad.write_bytes(b'{"jobs": [{"job_id": "\xc9\xf1"}]}')
    jobs, details, err = load_upstream_results(str(bad), str(tmp_path / "no.json"))
    assert jobs == [] and details == {}
    assert err and ("损坏" in err or "读取" in err)
