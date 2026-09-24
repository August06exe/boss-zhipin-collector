import json
import os

from app.settings import DEFAULT_SETTINGS, SettingsStore, default_data_dir


def test_missing_file_returns_defaults(tmp_path):
    store = SettingsStore(str(tmp_path))
    loaded = store.load()
    for key in DEFAULT_SETTINGS:
        assert key in loaded
    assert loaded["target_count"] == 300
    assert loaded["max_minutes"] == 300


def test_default_data_dir_is_downloads():
    assert os.path.basename(default_data_dir()) == "Downloads"


def test_save_patch_roundtrip_and_unknown_key_dropped(tmp_path):
    store = SettingsStore(str(tmp_path))
    saved = store.save({"target_count": 150, "hack": True})
    assert saved["target_count"] == 150
    assert "hack" not in saved
    again = SettingsStore(str(tmp_path)).load()
    assert again["target_count"] == 150


def test_chinese_dir_roundtrip(tmp_path):
    cdir = tmp_path / "我的数据"
    store = SettingsStore(str(cdir))
    store.save({"city": "杭州"})
    assert SettingsStore(str(cdir)).load()["city"] == "杭州"


def test_corrupted_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{bad json", encoding="utf-8")
    loaded = SettingsStore(str(tmp_path)).load()
    assert loaded["target_count"] == DEFAULT_SETTINGS["target_count"]


def test_saved_file_is_valid_json_with_utf8(tmp_path):
    store = SettingsStore(str(tmp_path))
    store.save({"keyword": "前端"})
    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert json.loads(raw)["keyword"] == "前端"
