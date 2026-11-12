import ctypes
import json
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CATALOG = json.loads((ROOT / "translations.json").read_text(encoding="utf-8"))
ENGLISH = "en"
POLISH = "pl-PL"
AUTO = "auto"
SPEECH_LOCALES = {
    item["speech"]: code for code, item in reversed(tuple(CATALOG.items()))
    if code != "hi-Latn"
}
SPEECH_LOCALES.update({"zh": "zh-CN", "hi": "hi-IN", "pt": "pt-BR", "es": "es-ES"})
RTL_LANGUAGES = {"ar", "fa", "ur"}


def best_locale(tag):
    tag = tag.replace("_", "-").lower()
    for code in CATALOG:
        if code.lower() == tag:
            return code
    primary = tag.split("-")[0]
    if primary == "zh" and tag.startswith("zh-hant"):
        return "zh-HK" if tag.endswith("-hk") else "zh-TW"
    if primary == "no":
        return "nb-NO"
    return SPEECH_LOCALES.get(primary, ENGLISH)


def windows_locale():
    # Windows returns an ordered, double-NUL-terminated list of UI language tags.
    size, count = ctypes.c_ulong(), ctypes.c_ulong()
    preferred = ctypes.windll.kernel32.GetUserPreferredUILanguages
    mui_language_name = 0x8
    if preferred(mui_language_name, ctypes.byref(count), None, ctypes.byref(size)) and size.value:
        names = ctypes.create_unicode_buffer(size.value)
        if preferred(mui_language_name, ctypes.byref(count), names, ctypes.byref(size)):
            return best_locale(names.value)
    return ENGLISH


def strings(locale):
    return CATALOG[locale]["strings"]


def normalize_control_name(name):
    normalized = unicodedata.normalize("NFKC", name)
    return " ".join("".join(ch for ch in normalized if unicodedata.category(ch) != "Cf").split())


def voice_control_labels():
    data = json.loads((ROOT / "codex_voice_labels.json").read_text(encoding="utf-8"))
    return {kind: {normalize_control_name(name) for name in names} for kind, names in data.items()}
