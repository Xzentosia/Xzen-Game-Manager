import os

from .constants import (
    MANUAL_CONTENT_FOLDER_NAME,
    MANUAL_LIBRARY_FOLDER_NAMES,
    MANUAL_LIBRARY_SCAN_SUBDIRS,
)
from .stores import is_ignored_store_folder
from .system import find_game_executable, is_path_inside


def is_drive_root_path(path):
    path = os.path.abspath(str(path or "").strip().strip('"'))
    drive, tail = os.path.splitdrive(path)
    return bool(drive) and tail.strip("\\/") == ""


def manual_game_from_folder(path, path_allowed_fn, name=None, exe_path=None):
    selected_folder = os.path.abspath(str(path or "").strip().strip('"'))

    ok, reason = path_allowed_fn(selected_folder)
    if not ok:
        return None, reason

    folder_name = name or os.path.basename(selected_folder.rstrip("\\/"))

    if exe_path:
        exe_path = os.path.abspath(str(exe_path or "").strip().strip('"'))

        if not os.path.isfile(exe_path):
            return None, "Selected executable does not exist."

        if not exe_path.lower().endswith(".exe"):
            return None, "Selected file is not an .exe."

        if not is_path_inside(exe_path, selected_folder):
            return None, "Selected executable must be inside the selected folder."
    else:
        exe_path = find_game_executable(selected_folder, max_depth=6, max_entries=25000)
        if not exe_path:
            return None, "No probable game executable found."

    game_path = selected_folder
    if folder_name.lower() == MANUAL_CONTENT_FOLDER_NAME.lower():
        game_path = selected_folder
        folder_name = os.path.basename(os.path.dirname(game_path.rstrip("\\/"))) or folder_name

    return {
        "appid": "",
        "name": folder_name,
        "path": game_path,
        "source": "Manual",
        "poster": "",
        "poster_status": "Manual Folder",
        "size": 0,
        "manifest_size": 0,
        "compressed_size": 0,
        "compressed_file_count": 0,
        "compression_algorithm": "",
        "file_count": 0,
        "exe_path": exe_path,
        "scan_progress": 0,
        "status": "Queued",
        "size_source": "Unknown",
    }, "OK"


def resolve_manual_game_folder(selected_folder, exe_path, path_allowed_fn):
    selected_folder = os.path.abspath(str(selected_folder or "").strip().strip('"'))
    ok, _ = path_allowed_fn(selected_folder)
    if ok:
        return selected_folder

    exe_path = os.path.abspath(str(exe_path or "").strip().strip('"'))
    exe_dir = os.path.dirname(exe_path)

    ok, _ = path_allowed_fn(exe_dir)
    if ok:
        return exe_dir

    return selected_folder


def is_manual_library_folder(name):
    lower = str(name or "").strip().lower()
    return lower in MANUAL_LIBRARY_FOLDER_NAMES


def manual_games_from_selected_folder(path, path_allowed_fn):
    direct_game, _ = manual_game_from_folder(path, path_allowed_fn)
    if direct_game:
        return [direct_game]

    scan_roots = []
    seen_scan_roots = set()
    for candidate in [path] + [os.path.join(path, rel) for rel in MANUAL_LIBRARY_SCAN_SUBDIRS]:
        if not os.path.isdir(candidate):
            continue
        resolved = os.path.abspath(candidate)
        key = resolved.lower()
        if key in seen_scan_roots:
            continue
        seen_scan_roots.add(key)
        scan_roots.append(resolved)

    found = []
    seen_paths = set()

    for scan_root in scan_roots:
        try:
            children = [item for item in os.scandir(scan_root) if item.is_dir()]
        except Exception:
            children = []

        for child in children:
            if is_ignored_store_folder(child.name):
                continue

            child_game, _ = manual_game_from_folder(child.path, path_allowed_fn, child.name)
            if child_game:
                key = os.path.abspath(child_game.get("path", "")).lower()
                if key not in seen_paths:
                    seen_paths.add(key)
                    found.append(child_game)
                continue

            content_path = os.path.join(child.path, MANUAL_CONTENT_FOLDER_NAME)
            if os.path.isdir(content_path):
                content_game, _ = manual_game_from_folder(content_path, path_allowed_fn, child.name)
                if content_game:
                    key = os.path.abspath(content_game.get("path", "")).lower()
                    if key not in seen_paths:
                        seen_paths.add(key)
                        found.append(content_game)

    return found
