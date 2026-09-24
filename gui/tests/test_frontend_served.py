from app.settings import SettingsStore
from test_flask_api import FakeController

from app.flask_app import create_app


def test_index_and_assets_served(tmp_path):
    app = create_app(FakeController(), SettingsStore(str(tmp_path)), token="t")
    tc = app.test_client()
    html = tc.get("/?t=t")
    assert html.status_code == 200
    assert b"screen-form" in html.data
    assert b"screen-login" in html.data
    assert b"screen-run" in html.data
    assert tc.get("/app.js?t=t").status_code == 200
    assert tc.get("/style.css?t=t").status_code == 200
