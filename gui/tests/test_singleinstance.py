import os

from app.singleinstance import acquire, read_runtime, write_runtime


def test_second_acquire_fails_same_name(tmp_path):
    os.environ["SINGLEINSTANCE_DIR"] = str(tmp_path)
    first = acquire("boss-gui-test")
    assert first is not None
    assert acquire("boss-gui-test") is None


def test_runtime_file_roundtrip(tmp_path):
    write_runtime(str(tmp_path), 9222, "tok")
    data = read_runtime(str(tmp_path))
    assert data == {"port": 9222, "token": "tok"}


def test_release_removes_lockfile(tmp_path):
    os.environ["SINGLEINSTANCE_DIR"] = str(tmp_path)
    lock = acquire("boss-gui-test2")
    from app.singleinstance import release
    release(lock, "boss-gui-test2")
    assert acquire("boss-gui-test2") is not None


def test_global_registry_roundtrip(tmp_path, monkeypatch):
    from app.singleinstance import read_global, write_global

    monkeypatch.setenv("BOSS_GUI_GLOBAL_DIR", str(tmp_path))
    write_global({"port": 8600, "token": "tok", "pid": 123, "root": "D:/x"})
    data = read_global()
    assert data["port"] == 8600
    assert data["pid"] == 123
    assert data["root"] == "D:/x"


def test_global_registry_missing_returns_none(tmp_path, monkeypatch):
    from app.singleinstance import read_global

    monkeypatch.setenv("BOSS_GUI_GLOBAL_DIR", str(tmp_path / "none"))
    assert read_global() is None
