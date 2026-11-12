import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from uuid import UUID

import psutil

from localization import normalize_control_name


class ChatAccessError(RuntimeError):
    pass


def codex_cli():
    for process in psutil.process_iter(("name", "exe")):
        name, executable = process.info["name"], process.info["exe"]
        if not executable or not name or name.casefold() != "chatgpt.exe":
            continue
        app = Path(executable).parent
        candidate = app / "resources" / "codex.exe"
        if app.parent.name.casefold().startswith("openai.codex_") and candidate.is_file():
            return str(candidate)
    command = shutil.which("codex.exe")
    if command:
        return str(Path(command).absolute())
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8; (Get-AppxPackage -Name OpenAI.Codex).InstallLocation"],
            capture_output=True, timeout=8, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
            text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ChatAccessError("Nie znaleziono programu Codex.") from exc
    for location in result.stdout.splitlines():
        location = location.strip()
        if not location:
            continue
        path = Path(location) / "app" / "resources" / "codex.exe"
        if path.is_file():
            return str(path)
    raise ChatAccessError("Nie znaleziono programu Codex.")


def chat_uuid(value):
    if not isinstance(value, str):
        raise ValueError("Invalid Codex chat identifier.")
    canonical = str(UUID(value))
    if canonical != value.lower():
        raise ValueError("Invalid Codex chat identifier.")
    return canonical


def chat_link(chat_id):
    return f"codex://threads/{chat_uuid(chat_id)}"


def list_chats():
    """Read named local conversations through the Codex App Server."""
    responses = queue.Queue()
    deadline = time.monotonic() + 10
    try:
        process = subprocess.Popen(
            [codex_cli(), "app-server", "-c", "mcp_servers={}"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError as exc:
        raise ChatAccessError("Nie udało się uruchomić odczytu czatów Codexa.") from exc

    def read_responses():
        try:
            for line in process.stdout:
                message = json.loads(line)
                if isinstance(message, dict) and "id" in message:
                    responses.put(message)
        except (OSError, ValueError):
            pass
        finally:
            responses.put(None)

    reader = threading.Thread(target=read_responses, name="codex-chat-list", daemon=True)
    reader.start()

    def send(method, params=None, request_id=None):
        request = {"method": method}
        if params is not None:
            request["params"] = params
        if request_id is not None:
            request["id"] = request_id
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        if request_id is None:
            return None
        try:
            reply = responses.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty as exc:
            raise ChatAccessError("Codex nie zwrócił listy czatów w wyznaczonym czasie.") from exc
        if reply is None or reply.get("id") != request_id or not isinstance(reply.get("result"), dict):
            raise ChatAccessError("Codex nie udostępnił listy czatów.")
        return reply["result"]

    try:
        send("initialize", {"clientInfo": {
            "name": "codex_voice_control", "title": "Codex Voice Control", "version": "0.1.0",
        }}, 0)
        send("initialized")
        rows, cursors = {}, set()
        params = {"limit": 100, "sortKey": "updated_at", "archived": False,
                  "useStateDbOnly": True, "currentAccountOnly": True}
        request_id = 1
        while time.monotonic() < deadline:
            result = send("thread/list", params, request_id)
            entries = result["data"]
            if not isinstance(entries, list):
                raise ChatAccessError("Codex zwrócił nieprawidłową listę czatów.")
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                title = entry.get("name")
                if isinstance(title, str) and title.strip():
                    try:
                        chat_id = chat_uuid(entry.get("id"))
                    except ValueError:
                        continue
                    rows[chat_id] = title.strip()
            cursor = result.get("nextCursor")
            if not cursor:
                counts = Counter(normalize_control_name(title).casefold() for title in rows.values())
                return [(chat_id, title) for chat_id, title in rows.items()
                        if counts[normalize_control_name(title).casefold()] == 1]
            if cursor in cursors:
                break
            cursors.add(cursor)
            params["cursor"] = cursor
            request_id += 1
        raise ChatAccessError("Codex nie zwrócił kompletnej listy czatów.")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ChatAccessError("Nie udało się odczytać czatów Codexa.") from exc
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(timeout=0.5)
        process.stdout.close()
