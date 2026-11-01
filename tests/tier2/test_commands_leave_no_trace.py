"""Every command, run as a person runs it: it leaves the checkout as it found it."""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Python on some machines writes no bytecode whatever is asked of it, so this turns writing on
# first: from there on, only the command itself can turn it off.
RUN = "import runpy, sys; sys.dont_write_bytecode = False; sys.argv = sys.argv[1:]; " \
      "runpy.run_path(sys.argv[0], run_name='__main__')"


@pytest.mark.parametrize("command", ["read-doc", "comment-doc", "google-sign-in", "watch-doc"])
def test_a_run_writes_no_bytecode_into_the_checkout(tmp_path, command):
    package = tmp_path / "googledocstools"
    package.mkdir()
    for name in os.listdir(os.path.join(HERE, "googledocstools")):
        if name.endswith(".py"):
            shutil.copy(os.path.join(HERE, "googledocstools", name), str(package))
    shutil.copy(os.path.join(HERE, command), str(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", RUN, str(tmp_path / command), "--help"], cwd=str(tmp_path),
        capture_output=True, text=True, env={"PATH": os.environ["PATH"]}, check=False,
    )
    assert done.returncode == 0 and done.stderr == ""
    assert [path.name for path in tmp_path.rglob("__pycache__")] == []
