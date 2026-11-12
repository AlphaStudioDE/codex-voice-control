from pathlib import Path


APP_NAME = "Codex Voice Control"
LEGACY_APP_NAME = "Friday Voice"
APP_ROOT = Path(__file__).resolve().parent
INSTALL_ROOT = APP_ROOT.parent if "__compiled__" in globals() else APP_ROOT

# Existing shortcuts, MCP profiles and scheduled tasks keep working after renaming.
TASK_NAME = f"{LEGACY_APP_NAME} Listener"
TRAY_CLASS_PREFIX = "FridayVoiceTray."
