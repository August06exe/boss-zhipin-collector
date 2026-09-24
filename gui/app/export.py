import csv
import json
import os
from datetime import datetime

from app.fields import FIELDS, filter_record
from app.settings import atomic_write_json


def task_dir(data_dir: str, name: str) -> str:
    path = os.path.join(data_dir, name)
    os.makedirs(path, exist_ok=True)
    return path


def _raw_dir(task_dir_path: str) -> str:
    path = os.path.join(task_dir_path, "raw")
    os.makedirs(path, exist_ok=True)
    return path


def save_master(task_dir_path: str, master: dict) -> None:
    atomic_write_json(os.path.join(_raw_dir(task_dir_path), "master.json"), master)


def load_master(task_dir_path: str) -> dict:
    path = os.path.join(_raw_dir(task_dir_path), "master.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def archive_round(task_dir_path: str, round_no: int, cycle_jobs: list) -> None:
    atomic_write_json(
        os.path.join(_raw_dir(task_dir_path), f"round_{round_no}.json"), cycle_jobs)


def _read_json(path):
    """utf-8-sig 兼容 BOM；编码/格式损坏抛 ValueError（调用方按本轮失败处理）。"""
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig")
    return json.loads(text)


def load_upstream_results(list_path, detail_path):
    """返回 (jobs, details_by_id, err)；err 非空为中文失败原因。"""
    try:
        payload = _read_json(list_path)
    except OSError as e:
        return [], {}, f"读取抓取结果失败：{e}"
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        return [], {}, f"抓取结果文件损坏：{e}"
    if not isinstance(payload, (dict, list)):
        return [], {}, "抓取结果文件格式异常"
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else payload
    if not isinstance(jobs, list):
        jobs = []
    details_by_id = {}
    try:
        raw_details = _read_json(detail_path)
    except (OSError, json.JSONDecodeError, ValueError):
        raw_details = []
    if isinstance(raw_details, dict):
        raw_details = list(raw_details.values())
    if isinstance(raw_details, dict):
        raw_details = list(raw_details.values())
    if not isinstance(raw_details, list):
        raw_details = []
    for d in raw_details or []:
        if not isinstance(d, dict):
            continue
        uid = str(d.get("job_id") or "")
        if uid:
            d = dict(d)
            # 引擎详情文件的描述键是 jd，归一为导出口径的 job_description
            if not d.get("job_description") and d.get("jd"):
                d["job_description"] = d["jd"]
            details_by_id[uid] = d
    return jobs or [], details_by_id, ""


def build_meta(task_name: str, form: dict, rounds: list, master: dict) -> dict:
    return {
        "任务": task_name,
        "搜索条件": {k: form.get(k) for k in
                     ("keywords", "cities", "salary", "experience", "degree", "scale", "pages")},
        "字段字典": [{"key": f["key"], "表头": f["csv"]} for f in FIELDS],
        "轮次": rounds,
        "统计": {"总数": len(master) if master is not None else 0},
        "生成时间": datetime.now().isoformat(timespec="seconds"),
    }


def export_task(task_dir_path: str, selection: list, meta: dict) -> None:
    master = load_master(task_dir_path)
    records = [filter_record(rec, selection) for rec in master.values()]
    meta = dict(meta or {})
    meta["统计"] = {"总数": len(master)}
    meta.setdefault("生成时间", datetime.now().isoformat(timespec="seconds"))
    atomic_write_json(os.path.join(task_dir_path, "jobs.json"), records)

    csv_tmp = os.path.join(task_dir_path, "jobs.csv.tmp")
    with open(csv_tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        chosen = [k for k in (selection if selection else [x["key"] for x in FIELDS])
                  if any(x["key"] == k for x in FIELDS)]
        writer.writerow([next(x["csv"] for x in FIELDS if x["key"] == k) for k in chosen])
        for rec in records:
            writer.writerow([rec.get(k, "") for k in chosen])
        f.flush()
        os.fsync(f.fileno())
    os.replace(csv_tmp, os.path.join(task_dir_path, "jobs.csv"))

    atomic_write_json(os.path.join(task_dir_path, "meta.json"), meta)
