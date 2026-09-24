import pytest

from app.flask_app import create_app
from app.settings import SettingsStore


class FakeController:
    def __init__(self):
        self.stopped = False
        self.started_form = None
        self.state_data = {"state": "idle", "task": "", "task_dir": "",
                           "stats": {"total": 0}, "rounds": [], "logs": [],
                           "interval_seconds": 1800, "deadline_at": 0,
                           "next_round_at": 0, "browser": "",
                           "browser_missing": False}

    def state(self):
        return self.state_data

    def start(self, form):
        if not form.get("keywords"):
            return {"error": "请至少填写一个关键词"}
        self.started_form = form
        return {"ok": True}

    def stop(self):
        self.stopped = True

    def login_start_browser(self):
        pass

    def login_verify(self):
        return True

    def cleanup_stale_browser(self):
        pass


@pytest.fixture()
def client(tmp_path):
    settings = SettingsStore(str(tmp_path))
    ctrl = FakeController()
    app = create_app(ctrl, settings, token="secret")
    return app.test_client(), ctrl


def test_token_required(client):
    tc, _ = client
    assert tc.get("/api/state").status_code == 401
    assert tc.get("/api/state?t=secret").status_code == 200


def test_state_and_fields(client):
    tc, _ = client
    st = tc.get("/api/state?t=secret").get_json()
    assert st["state"] == "idle"
    fields = tc.get("/api/fields?t=secret").get_json()
    assert len(fields) == 16
    assert fields[0]["csv"] == "职位名称"


def test_settings_get_and_post(client):
    tc, _ = client
    r = tc.post("/api/settings?t=secret", json={"target_count": 150})
    assert r.get_json()["target_count"] == 150
    g = tc.get("/api/settings?t=secret").get_json()
    assert g["target_count"] == 150


def test_start_passes_form_and_error_path(client):
    tc, ctrl = client
    ok = tc.post("/api/start?t=secret", json={"keywords": ["前端"]}).get_json()
    assert ok == {"ok": True}
    assert ctrl.started_form["keywords"] == ["前端"]
    bad = tc.post("/api/start?t=secret", json={}).get_json()
    assert "关键词" in bad["error"]


def test_stop_and_login_and_cleanup(client):
    tc, ctrl = client
    assert tc.post("/api/stop?t=secret").status_code == 200
    assert ctrl.stopped is True
    assert tc.post("/api/login/start-browser?t=secret").status_code == 200
    assert tc.post("/api/login/verify?t=secret").get_json() == {"ok": True}
    assert tc.post("/api/browser/cleanup?t=secret").status_code == 200


def test_choose_dir_returns_path_or_none(client, monkeypatch):
    tc, _ = client
    import app.flask_app as fa
    monkeypatch.setattr(fa, "choose_folder", lambda: None)
    data = tc.post("/api/choose-dir?t=secret").get_json()
    assert data == {"path": None}


def test_export_missing_task_404(client):
    tc, _ = client
    r = tc.post("/api/export?t=secret", json={"task_dir": "不存在"})
    assert r.status_code == 404


def test_static_assets_open_but_api_guarded(client):
    tc, _ = client
    assert tc.get("/app.js").status_code == 200
    assert tc.get("/style.css").status_code == 200
    assert tc.get("/").status_code == 200
    assert tc.get("/api/state").status_code == 401


def test_auth_fail_closed_wrong_header_with_right_query(client):
    tc, _ = client
    r = tc.get("/api/state?t=secret", headers={"X-Token": "WRONG"})
    assert r.status_code == 401
    r2 = tc.get("/api/state", headers={"X-Token": "secret"})
    assert r2.status_code == 200
