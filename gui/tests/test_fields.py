from app.fields import FIELDS, field_keys, filter_record


def test_catalog_has_16_fields_unique_keys():
    keys = field_keys()
    assert len(keys) == 16
    assert len(set(keys)) == 16
    assert "title" in keys and "job_description" in keys


def test_company_name_maps_from_boss_name():
    f = next(x for x in FIELDS if x["key"] == "company_name")
    assert f["source"] == "boss_name"
    assert f["csv"] == "公司名称"


def test_filter_record_selection_and_order():
    rec = {"title": "前端", "salary": "20-30K", "boss_name": "示例公司", "extra": "x"}
    out = filter_record(rec, ["salary", "title"])
    assert out == {"title": "前端", "salary": "20-30K"}


def test_empty_selection_means_all():
    rec = {"title": "前端", "boss_name": "示例公司", "extra": "x"}
    out = filter_record(rec, [])
    assert out["title"] == "前端"
    assert out["company_name"] == "示例公司"
    assert "extra" not in out
