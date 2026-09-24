from app.merge import merge_into


def test_new_and_updated_and_stats():
    master = {"abc": {"job_id": "abc", "title": "旧岗位", "salary": "10K", "first_seen": "t0", "last_seen": "t0"}}
    now = "t1"
    stats = merge_into(master, [
        {"job_id": "abc", "title": "旧岗位", "salary": "15K"},
        {"job_id": "def", "title": "新岗位", "salary": "20K"},
        {"title": "无ID脏数据"},
    ], now)
    assert stats == {"new": 1, "updated": 1, "total": 2}
    assert master["abc"]["salary"] == "15K"
    assert master["abc"]["last_seen"] == "t1"
    assert master["abc"]["first_seen"] == "t0"
    assert master["def"]["first_seen"] == "t1"
    assert master["def"]["last_seen"] == "t1"


def test_empty_new_value_does_not_overwrite():
    master = {"abc": {"job_id": "abc", "title": "旧岗位", "welfare": "五险"}}
    merge_into(master, [{"job_id": "abc", "welfare": ""}], "t1")
    assert master["abc"]["welfare"] == "五险"
