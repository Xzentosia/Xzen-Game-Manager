import os
import time
import shutil
from pathlib import Path
def format_game_size(num_bytes):
    try:
        num_bytes = int(num_bytes)
    except Exception:
        num_bytes = 0

    if num_bytes <= 0:
        return "0 GB"

    mb = num_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.2f} MB"


def drive_label_for_path(path):
    try:
        drive = os.path.splitdrive(os.path.abspath(path))[0]
        if drive:
            return drive.upper()
        anchor = Path(path).anchor
        return anchor.rstrip("\\/") or "Drive"
    except Exception:
        return "Drive"


def get_drive_free_bytes(path):
    try:
        usage_path = os.path.abspath(path)
        if not os.path.exists(usage_path):
            drive = os.path.splitdrive(usage_path)[0]
            if drive:
                usage_path = drive + "\\"
        return int(shutil.disk_usage(usage_path).free)
    except Exception:
        return None


def drive_space_progress_text(path, start_free):
    current_free = get_drive_free_bytes(path)
    if current_free is None:
        return ""

    drive_label = drive_label_for_path(path)
    if start_free is None:
        return f"{drive_label}: {format_game_size(current_free)} free"

    used_back = int(start_free) - current_free
    if used_back >= 0:
        change = f"Decompressed space used: {format_game_size(used_back)}"
    else:
        change = f"Free space change: +{format_game_size(abs(used_back))}"
    return f"{drive_label}: {format_game_size(current_free)} free | {change}"


def format_eta(seconds):
    try:
        seconds = int(seconds)
    except Exception:
        return "calculating..."

    if seconds <= 0:
        return "less than 1 sec"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m left"
    if minutes > 0:
        return f"{minutes}m {secs}s left"
    return f"{secs}s left"


def format_elapsed(seconds):
    try:
        seconds = int(seconds)
    except Exception:
        return "0s"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def global_eta_from_percent(start_time, percent, allow_eta=True):
    if not allow_eta:
        return "paused"

    percent = max(0, min(100, int(percent or 0)))
    if percent <= 1:
        return "calculating..."
    if percent >= 100:
        return "done"

    elapsed = max(0.1, time.time() - start_time)
    seconds_per_percent = elapsed / percent
    remaining_percent = 100 - percent
    return format_eta(seconds_per_percent * remaining_percent)


def global_progress_text(status, percent, start_time, allow_eta=True):
    percent = max(0, min(100, int(percent or 0)))
    elapsed = format_elapsed(time.time() - start_time)
    eta = global_eta_from_percent(start_time, percent, allow_eta)
    return f"{status}\nGlobal progress: {percent}% | Elapsed: {elapsed} | ETA: {eta}"

