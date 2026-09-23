"""Run the Streamlit app headlessly and make sure it renders without exceptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "src" / "ridethewave" / "ui" / "app.py"


def test_dashboard_renders():
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == "Ride The Wave"
    assert len(at.tabs) == 4
