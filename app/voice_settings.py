import ctypes
import json
import os
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from branding import APP_NAME, LEGACY_APP_NAME
from chimes import DEFAULT_SOUNDS, TONES
from codex_chats import chat_uuid
from localization import AUTO, CATALOG, POLISH, SPEECH_LOCALES, strings, windows_locale


ROOT = Path(__file__).resolve().parent
LEGACY_PHRASES = ROOT / "Frazy startowe.txt"
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", ROOT))
SETTINGS_PATH = DATA_ROOT / APP_NAME / "frazy.json"
LEGACY_SETTINGS_PATH = DATA_ROOT / LEGACY_APP_NAME / "frazy.json"
DEFAULT_STARTS = ("Friday, zgłoś się", "Friday, jesteś?", "Friday, słuchaj", "Friday, a co myślisz?")
DEFAULT_STOP = "bez odbioru"
LAYOUTS = ("split", "sidebar", "compact")
DEFAULT_LAYOUT = "compact"


@dataclass(frozen=True)
class VoicePhrases:
    starts: tuple[str, ...]
    stops: tuple[str, ...]
    ui_locale: str = POLISH
    speech_language: str = "pl"
    sounds: dict[str, str] = field(default_factory=DEFAULT_SOUNDS.copy)
    layout: str = DEFAULT_LAYOUT
    chat_id: str | None = None
    auto_replay: bool = True


def phrase_words(text, language="pl"):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    if language == "zh" and normalized:
        # Use the same form for traditional and simplified Chinese commands.
        convert = ctypes.windll.kernel32.LCMapStringEx
        simplified_chinese = 0x02000000
        count = convert("zh-CN", simplified_chinese, normalized, -1, None, 0, None, None, 0)
        if count:
            buffer = ctypes.create_unicode_buffer(count)
            if convert("zh-CN", simplified_chinese, normalized, -1, buffer, count, None, None, 0):
                normalized = buffer.value
    words = "".join(
        char if unicodedata.category(char)[0] in "LMN" else " "
        for char in normalized
        if not 0x064B <= ord(char) <= 0x065F and char not in "\u0640\u0670\u200c\u200d"
    ).split()
    if words and language in {"pl", AUTO} and words[0] in {"frajdej", "frejdej"}:
        words[0] = "friday"
    # Whisper can insert or omit spaces in scripts that do not require word separators.
    if language in {"ja", "my", "th", "zh"} or (
        language == AUTO and any(
            0x0E00 <= ord(char) <= 0x0E7F or 0x1000 <= ord(char) <= 0x109F
            or 0x3040 <= ord(char) <= 0x30FF or 0x3400 <= ord(char) <= 0x9FFF
            for char in normalized
        )
    ):
        return ("".join(words),) if words else ()
    return tuple(words)


def validate_phrases(starts, stops, ui_locale=POLISH, speech_language="pl", sounds=None,
                     layout=DEFAULT_LAYOUT, chat_id=None, auto_replay=True):
    if (not isinstance(ui_locale, str) or ui_locale not in CATALOG
            or not isinstance(speech_language, str)
            or (speech_language != AUTO and speech_language not in SPEECH_LOCALES)):
        raise ValueError("Unsupported language setting.")
    if isinstance(stops, str):
        stops = (stops,)

    def clean(lines):
        if not isinstance(lines, (list, tuple)) or any(
            not isinstance(line, str) or len(line.splitlines()) > 1 for line in lines
        ):
            raise ValueError("Enter one phrase per line.")
        unique = {}
        for line in lines:
            if words := phrase_words(line, speech_language):
                unique.setdefault(words, line.strip())
        return unique

    starts, stops = clean(starts), clean(stops)
    if not starts or not stops or starts.keys() & stops.keys():
        raise ValueError("Enter different start and stop phrases.")
    if sounds is None:
        sounds = {}
    if not isinstance(sounds, dict) or any(
        event not in DEFAULT_SOUNDS or tone not in TONES for event, tone in sounds.items()
    ):
        raise ValueError("Unsupported sound setting.")
    if layout not in LAYOUTS:
        raise ValueError("Unsupported settings layout.")
    if chat_id is not None:
        chat_id = chat_uuid(chat_id)
    if not isinstance(auto_replay, bool):
        raise ValueError("Unsupported automatic replay setting.")
    return VoicePhrases(tuple(starts.values()), tuple(stops.values()), ui_locale, speech_language,
                        DEFAULT_SOUNDS | sounds, layout, chat_id, auto_replay)


def default_phrases(locale=None):
    ui_locale = locale or windows_locale()
    speech_language = CATALOG[ui_locale]["speech"]
    if ui_locale == POLISH:
        return VoicePhrases(DEFAULT_STARTS, (DEFAULT_STOP,))
    speech_text = strings("hi-IN" if ui_locale == "hi-Latn" else ui_locale)
    return VoicePhrases(
        (speech_text["default_start"],), (speech_text["default_stop"],), ui_locale, speech_language,
    )


def load_phrases():
    for path in (SETTINGS_PATH, LEGACY_SETTINGS_PATH):
        try:
            contents = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            continue
        break
    else:
        try:
            starts = LEGACY_PHRASES.read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            return default_phrases()
        return validate_phrases(starts, DEFAULT_STOP)
    data = json.loads(contents)
    if not isinstance(data, dict):
        raise ValueError("Plik fraz musi zawierać ustawienia startu i zakończenia.")
    return validate_phrases(data.get("starts"), data.get("stops", data.get("stop")),
                            data.get("ui_locale", POLISH), data.get("speech_language", "pl"),
                            data.get("sounds"), data.get("layout", DEFAULT_LAYOUT), data.get("chat_id"),
                            data.get("auto_replay", True))


def phrase_revision():
    for path in (SETTINGS_PATH, LEGACY_SETTINGS_PATH, LEGACY_PHRASES):
        try:
            info = path.stat()
            return path, info.st_mtime_ns, info.st_size
        except FileNotFoundError:
            continue
    return None


def save_phrases(starts, stops, ui_locale=POLISH, speech_language="pl", sounds=None,
                 layout=DEFAULT_LAYOUT, chat_id=None, auto_replay=True):
    settings = validate_phrases(starts, stops, ui_locale, speech_language, sounds, layout, chat_id, auto_replay)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=SETTINGS_PATH.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
        temporary.replace(SETTINGS_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return settings
