FIELDS = [
    {"key": "title", "csv": "职位名称", "source": "title"},
    {"key": "salary", "csv": "薪资", "source": "salary"},
    {"key": "location", "csv": "地点", "source": "location"},
    {"key": "experience_degree", "csv": "经验学历", "source": "tags"},
    {"key": "company_name", "csv": "公司名称", "source": "boss_name"},
    {"key": "recruiter_title", "csv": "招聘者头衔", "source": "boss_title"},
    {"key": "boss_active_status", "csv": "招聘者活跃状态", "source": "boss_active_status"},
    {"key": "company_scale", "csv": "公司规模", "source": "company_scale"},
    {"key": "company_stage", "csv": "融资阶段", "source": "company_stage"},
    {"key": "company_industry", "csv": "所属行业", "source": "company_industry"},
    {"key": "skills", "csv": "技能要求", "source": "skills"},
    {"key": "job_labels", "csv": "职位标签", "source": "job_labels"},
    {"key": "welfare", "csv": "福利待遇", "source": "welfare"},
    {"key": "job_description", "csv": "职位描述", "source": "job_description"},
    {"key": "job_link", "csv": "职位链接", "source": "job_link"},
    {"key": "company_link", "csv": "公司链接", "source": "company_link"},
]


def field_keys() -> list:
    return [f["key"] for f in FIELDS]


def csv_header(key: str) -> str:
    for f in FIELDS:
        if f["key"] == key:
            return f["csv"]
    return key


def filter_record(record: dict, keys: list) -> dict:
    chosen = keys if keys else field_keys()
    out = {}
    for key in chosen:
        for f in FIELDS:
            if f["key"] == key:
                out[key] = record.get(f["source"], "")
    return out
