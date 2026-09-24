import os
import subprocess
import sys

AUDIT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "packaging", "audit_imports.py")


def test_audit_passes_on_stdlib_only_dir(tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text("import os\nimport json\n", encoding="utf-8")
    r = subprocess.run([sys.executable, AUDIT, str(tmp_path)], capture_output=True)
    assert r.returncode == 0


def test_audit_fails_on_missing_module(tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text("import not_a_real_module_xyz\n", encoding="utf-8")
    r = subprocess.run([sys.executable, AUDIT, str(tmp_path)], capture_output=True)
    assert r.returncode == 1
