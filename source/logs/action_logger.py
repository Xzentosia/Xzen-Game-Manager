from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent
ALL_LOG = LOG_DIR / "actions.log"
SUCCESS_LOG = LOG_DIR / "success.log"
WARNING_LOG = LOG_DIR / "warnings.log"
ERROR_LOG = LOG_DIR / "errors.log"
DEBUG_LOG = LOG_DIR / "debug.log"
LOG_FILES = (ALL_LOG, SUCCESS_LOG, WARNING_LOG, ERROR_LOG, DEBUG_LOG)

_LOCK = threading.RLock()


def _sanitize(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    return str(value)


def _line(level, area, action, message, **context):
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "level": level,
        "area": str(area or "general"),
        "action": str(action or "event"),
        "message": str(message or ""),
        "context": _sanitize(context),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _write(path, line):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def log_action(level, area, action, message="", **context):
    normalized = str(level or "debug").lower()
    line = _line(normalized, area, action, message, **context)
    with _LOCK:
        _write(ALL_LOG, line)
        if normalized == "success":
            _write(SUCCESS_LOG, line)
        elif normalized in {"warning", "warn"}:
            _write(WARNING_LOG, line)
        elif normalized in {"error", "exception", "critical"}:
            _write(ERROR_LOG, line)
        else:
            _write(DEBUG_LOG, line)


def reset_logs():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        for path in LOG_FILES:
            path.write_text("", encoding="utf-8")


def log_debug(area, action, message="", **context):
    log_action("debug", area, action, message, **context)


def log_success(area, action, message="", **context):
    log_action("success", area, action, message, **context)


def log_warning(area, action, message="", **context):
    log_action("warning", area, action, message, **context)


def log_error(area, action, message="", **context):
    log_action("error", area, action, message, **context)


def log_exception(area, action, exc, message="", **context):
    log_action(
        "exception",
        area,
        action,
        message or str(exc),
        error_type=type(exc).__name__,
        error=str(exc),
        traceback=traceback.format_exc(),
        **context,
    )
