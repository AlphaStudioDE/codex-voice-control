import json
import queue
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from codex_chats import ChatAccessError, chat_uuid, codex_cli, list_chats
from localization import normalize_control_name


REPLAY_REQUESTS = {
    "pl": "Przeczytaj na głos swoją ostatnią gotową odpowiedź, bez wykonywania zadania ponownie.",
    "en": "Read your last completed answer aloud verbatim. Do not redo the task.",
}


def is_replay_request(turn):
    return any(
        request in part.get("text", "")
        for item in turn.get("items", []) if item.get("type") == "userMessage"
        for part in item.get("content", []) if part.get("type") == "text"
        for request in REPLAY_REQUESTS.values()
    )


class ReplayCancelled(Exception):
    pass


@dataclass(frozen=True)
class PendingAnswer:
    chat_id: str
    title: str
    turn_id: str


class ReplayConnection:
    def __init__(self, cancelled):
        self.cancelled = cancelled
        self.messages = queue.Queue()
        self.sequence = 0

    def __enter__(self):
        self.process = subprocess.Popen(
            [codex_cli(), "app-server", "-c", "mcp_servers={}"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
        )

        def read():
            try:
                for line in self.process.stdout:
                    self.messages.put(json.loads(line))
            except (OSError, ValueError):
                pass
            finally:
                self.messages.put(None)

        self.reader = threading.Thread(target=read, name="codex-voice-replay", daemon=True)
        self.reader.start()
        try:
            self.request("initialize", {
                "clientInfo": {"name": "codex_voice_control", "version": "0.1.0"},
            })
            self.send({"method": "initialized"})
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.join(timeout=1)
        self.process.stdout.close()

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self, deadline):
        while time.monotonic() < deadline:
            if self.cancelled.is_set():
                raise ReplayCancelled
            try:
                message = self.messages.get(timeout=min(0.15, max(0, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if message is None:
                raise ChatAccessError("Codex App Server disconnected during voice replay.")
            if isinstance(message, dict):
                return message
        raise TimeoutError("Codex did not respond in time.")

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 12
        while True:
            message = self.receive(deadline)
            if message.get("id") == request_id:
                if "error" in message:
                    error = message["error"]
                    raise ChatAccessError(f"{method}: {error.get('message', 'request failed')}")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise ChatAccessError(f"{method}: invalid response")
                return result

    def latest_turn(self, chat_id, *, full=False):
        result = self.request("thread/turns/list", {
            "threadId": chat_uuid(chat_id), "limit": 1, "sortDirection": "desc",
            "itemsView": "full" if full else "notLoaded",
        })
        return next(iter(result["data"]), None)


def completed_answer(turn, expected_turn_id=None):
    if (not turn or turn.get("status") != "completed"
            or (expected_turn_id is not None and turn.get("id") != expected_turn_id)):
        return None
    messages = [
        item["text"].strip() for item in turn["items"]
        if item.get("type") == "agentMessage" and item.get("phase") in (None, "final_answer")
        and isinstance(item.get("text"), str) and item["text"].strip()
    ]
    return "\n\n".join(messages) or None


def identify_work(title, call_started_at, cancelled):
    normalized = normalize_control_name(title).casefold()
    chat_id = next((key for key, name in list_chats()
                    if normalize_control_name(name).casefold() == normalized), None)
    if chat_id is None or cancelled.is_set():
        return None
    deadline = time.monotonic() + 25
    with ReplayConnection(cancelled) as connection:
        while time.monotonic() < deadline and not cancelled.is_set():
            turn = connection.latest_turn(chat_id, full=True)
            if (turn and turn.get("status") in {"inProgress", "interrupted"}
                    and turn.get("completedAt") is None
                    and isinstance(turn.get("startedAt"), int)
                    and turn["startedAt"] >= int(call_started_at)
                    and any(item.get("type") == "userMessage" for item in turn["items"])
                    and not is_replay_request(turn)):
                return PendingAnswer(chat_id, title, turn["id"])
            cancelled.wait(1)
    return None


def wait_for_answer(ticket, cancelled):
    deadline = time.monotonic() + 20 * 60
    with ReplayConnection(cancelled) as connection:
        while time.monotonic() < deadline and not cancelled.is_set():
            turn = connection.latest_turn(ticket.chat_id)
            if not turn or turn.get("id") != ticket.turn_id or turn.get("status") == "failed":
                return False
            if turn.get("status") == "completed":
                return completed_answer(connection.latest_turn(ticket.chat_id, full=True), ticket.turn_id) is not None
            cancelled.wait(2)
    return False


class AutomaticReplay:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cvc-voice")
        self.future = self.cancelled = self.ticket = None
        self.phase = None
        self.attempt_after = 0

    def submit(self, phase, operation, *args):
        self.phase = phase
        self.cancelled = threading.Event()
        self.future = self.executor.submit(operation, *args, self.cancelled)

    def cancel(self):
        if self.cancelled is not None:
            self.cancelled.set()
        if self.future is not None:
            self.future.cancel()
        self.future = self.cancelled = self.ticket = None
        self.phase = None

    def close(self):
        self.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def check(self, desktop, call_active, call_started_at):
        if self.future is None:
            if call_active and time.monotonic() >= self.attempt_after:
                title = desktop.voice_chat_title()
                if title:
                    self.attempt_after = time.monotonic() + 3
                    self.submit("identify", identify_work, title, call_started_at)
            return None
        if not self.future.done():
            return None
        phase, future, ticket = self.phase, self.future, self.ticket
        self.cancel()
        try:
            result = future.result()
        except ReplayCancelled:
            return None
        except (ChatAccessError, OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Automatyczny odczyt: {exc}", flush=True)
            return None
        if phase == "identify" and result and call_active and desktop.voice_chat_title() == result.title:
            if desktop.suspend_for_replay():
                self.ticket = result
                self.submit("wait", wait_for_answer, result)
                print("Wysłano polecenie rozłączenia głosu na czas pracy Codexa.", flush=True)
                return "suspended"
        if phase == "wait" and result and not call_active and not desktop.find_active_call():
            if desktop.open_call(ticket.chat_id):
                if desktop.request_replay(ticket.title):
                    print("Wysłano do Codexa prośbę o ponowny odczyt.", flush=True)
                    return "resumed"
                desktop.close_reopened_chat(ticket.title)
                print("Codex nie udostępnił pustego pola do wysłania prośby o odczyt.", flush=True)
        return None
