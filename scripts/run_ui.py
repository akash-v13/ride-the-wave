"""Launch the dashboard: uv run python scripts/run_ui.py"""

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "ridethewave" / "ui" / "app.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(APP), "--server.headless", "true"]))
