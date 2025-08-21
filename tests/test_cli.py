import subprocess
import sys


def test_cli_runs_help():
    res = subprocess.run(
        [sys.executable, "-m", "utils.pdf_utils", "--help"], capture_output=True
    )
    assert res.returncode == 0
