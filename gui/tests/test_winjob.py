import os
import subprocess
import sys

import pytest


def test_assign_off_windows_returns_none(monkeypatch):
    from app import winjob
    monkeypatch.setattr(winjob.os, "name", "posix")
    assert winjob.assign_child(0) is None


def test_spawn_and_terminate_child_smoke():
    if os.name != "nt":
        pytest.skip("仅 Windows")
    from app import winjob
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert winjob.assign_child(proc.pid) is not None
        winjob.terminate_children()
        rc = proc.wait(timeout=10)
        assert rc != 0
    finally:
        if proc.poll() is None:
            proc.kill()
