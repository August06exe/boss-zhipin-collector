def merge_into(master: dict, cycle_jobs: list, now: str) -> dict:
    stats = {"new": 0, "updated": 0, "total": len(master)}
    for job in cycle_jobs:
        uid = str(job.get("job_id") or "")
        if not uid:
            continue
        old = master.get(uid)
        if old is None:
            record = dict(job)
            record["first_seen"] = now
            record["last_seen"] = now
            master[uid] = record
            stats["new"] += 1
            stats["total"] += 1
        else:
            for key, value in job.items():
                if value not in (None, ""):
                    old[key] = value
            old["last_seen"] = now
            stats["updated"] += 1
    return stats
