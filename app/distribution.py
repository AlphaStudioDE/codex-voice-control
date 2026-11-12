import os
import sys


def main():
    mode = sys.argv.pop(1) if len(sys.argv) > 1 else "panel"
    if mode == "panel":
        from panel import main as run
    elif mode == "setup":
        from setup_support import main as run
    elif mode in {"listener", "mcp", "voice"}:
        if mode == "listener":
            sys.argv.append("--background")
        elif mode == "mcp":
            sys.argv.append("--mcp")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from friday import main as run
    else:
        raise SystemExit(f"Unknown mode: {mode}")
    run()


if __name__ == "__main__":
    main()
