"""main.py must load .env before app.core.config reads os.environ at import time."""
import os
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]


def test_dotenv_values_reach_settings(tmp_path):
    (tmp_path / "main.py").write_text((API_ROOT / "main.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("PORT=4321\nWORKERS=3\n", encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if k not in ("PORT", "WORKERS")}
    env["PYTHONPATH"] = str(API_ROOT)
    code = "import runpy; ns = runpy.run_path('main.py', run_name='imported'); print(ns['settings'].PORT, ns['settings'].WORKERS)"
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)

    assert out.returncode == 0, out.stderr
    assert out.stdout.split()[-2:] == ["4321", "3"]
