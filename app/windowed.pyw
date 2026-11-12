import runpy
import site
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODES = {
    "listener": ("friday.py", "--background"),
    "panel": ("panel.py",),
}


def main():
    script, *arguments = MODES[sys.argv[1]]
    target = ROOT / script
    venv_packages = ROOT / ".venv" / "Lib" / "site-packages"
    if venv_packages.is_dir():
        site.addsitedir(str(venv_packages))
    sys.argv = [str(target), *arguments]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log = ROOT / ".runtime" / "windowed-error.log"
        log.parent.mkdir(exist_ok=True)
        with log.open("a", encoding="utf-8") as stream:
            traceback.print_exc(file=stream)
        raise
