import json
import os

from .deps import get_logger, has_pydantic, pydantic
from .constants import (
    BACKGROUND_SELECTION_MODES,
    DATA_FILE,
    DEFAULT_COMPRESSION_ALGORITHM,
    DEFAULT_LAUNCH_AS_ADMIN,
    DEFAULT_WORKER_COUNT,
    DEFAULT_WORKER_MODE,
    AUTO_PAUSE_WHEN_GAME_RUNNING,
    SETTINGS_FILE,
    compression_algorithm_keys,
    normalized_worker_count,
    normalized_worker_mode,
)
from .stores import is_store_game_installed
from .system import safe_path

LOGGER = get_logger(__name__)
PYDANTIC_AVAILABLE = has_pydantic()

if PYDANTIC_AVAILABLE:
    BaseModel = pydantic.BaseModel                              
    ValidationError = pydantic.ValidationError                              

    class AppSettingsModel(BaseModel):
        compression_algorithm: str = DEFAULT_COMPRESSION_ALGORITHM
        initial_scan_done: bool = False
        show_terminal: bool = False
        launch_as_admin: bool = DEFAULT_LAUNCH_AS_ADMIN
        smart_game_pause: bool = AUTO_PAUSE_WHEN_GAME_RUNNING
        worker_mode: str = DEFAULT_WORKER_MODE
        worker_count: int = DEFAULT_WORKER_COUNT
        library_view_mode: str = "grid"
        background_selection_mode: str = "all"
        background_selected_paths: list[str] = []
        background_decompress_selected_paths: list[str] = []

        class Config:
            extra = "allow"

    class GameEntryModel(BaseModel):
        appid: str = ""
        name: str = "Unknown"
        path: str = ""
        source: str = "Manual"
        poster: str = ""
        poster_status: str = "Queued"
        size: int = 0
        original_size: int = 0
        manifest_size: int = 0
        compressed_size: int = 0
        compressed_file_count: int = 0
        compression_algorithm: str = ""
        file_count: int = 0
        exe_path: str = ""
        scan_progress: int = 0
        status: str = "Queued"
        size_source: str = "Unknown"

        class Config:
            extra = "allow"


def _safe_model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def default_app_settings():
    return {
        "compression_algorithm": DEFAULT_COMPRESSION_ALGORITHM,
        "initial_scan_done": False,
        "show_terminal": False,
        "launch_as_admin": DEFAULT_LAUNCH_AS_ADMIN,
        "smart_game_pause": AUTO_PAUSE_WHEN_GAME_RUNNING,
        "worker_mode": DEFAULT_WORKER_MODE,
        "worker_count": DEFAULT_WORKER_COUNT,
        "library_view_mode": "grid",
        "background_selection_mode": "all",
        "background_selected_paths": [],
        "background_decompress_selected_paths": [],
    }


def normalize_app_settings(settings):
    merged = default_app_settings()
    if isinstance(settings, dict):
        merged.update(settings)

    if merged.get("compression_algorithm") not in compression_algorithm_keys():
        merged["compression_algorithm"] = DEFAULT_COMPRESSION_ALGORITHM
    merged["launch_as_admin"] = bool(merged.get("launch_as_admin", DEFAULT_LAUNCH_AS_ADMIN))
    merged["smart_game_pause"] = bool(merged.get("smart_game_pause", AUTO_PAUSE_WHEN_GAME_RUNNING))
    merged["worker_mode"] = normalized_worker_mode(merged.get("worker_mode", DEFAULT_WORKER_MODE))
    merged["worker_count"] = normalized_worker_count(merged.get("worker_count", DEFAULT_WORKER_COUNT))
    if merged.get("library_view_mode") not in {"grid", "rows"}:
        merged["library_view_mode"] = "grid"
    if merged.get("background_selection_mode") not in BACKGROUND_SELECTION_MODES:
        merged["background_selection_mode"] = "all"
    if not isinstance(merged.get("background_selected_paths"), list):
        merged["background_selected_paths"] = []
    if not isinstance(merged.get("background_decompress_selected_paths"), list):
        merged["background_decompress_selected_paths"] = []

    if PYDANTIC_AVAILABLE:
        try:
            model = AppSettingsModel(**merged)
            return _safe_model_dump(model)
        except ValidationError as exc:
            LOGGER.warning("settings_validation_failed", error=str(exc))
        except Exception as exc:
            LOGGER.warning("settings_validation_error", error=str(exc))
    return merged


def load_app_settings(settings_file=SETTINGS_FILE):
    loaded = {}
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except Exception:
            loaded = {}
    return normalize_app_settings(loaded)


def save_app_settings(settings, settings_file=SETTINGS_FILE):
    parent = os.path.dirname(settings_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def normalize_game_entry(game):
    normalized = dict(game or {})
    normalized.setdefault("poster_status", "Queued" if not normalized.get("poster") else "Ready")
    normalized.setdefault("file_count", 0)
    normalized.setdefault("size", 0)
    normalized.setdefault("original_size", 0)
    normalized.setdefault("manifest_size", 0)
    normalized.setdefault("compressed_size", 0)
    normalized.setdefault("compressed_file_count", 0)
    normalized.setdefault("compression_algorithm", "")
    normalized.setdefault("exe_path", "")
    normalized.setdefault("scan_progress", 0)
    normalized.setdefault("status", "Queued")
    normalized.setdefault("size_source", "Unknown")
    if int(normalized.get("compressed_size", 0) or 0) < 0:
        normalized["compressed_size"] = 0
    for key in ("size", "original_size", "manifest_size", "compressed_size"):
        try:
            normalized[key] = max(0, int(normalized.get(key, 0) or 0))
        except Exception:
            normalized[key] = 0

    compressed_size = int(normalized.get("compressed_size", 0) or 0)
    size = int(normalized.get("size", 0) or 0)
    original_size = int(normalized.get("original_size", 0) or 0)
    manifest_size = int(normalized.get("manifest_size", 0) or 0)
    compressed_hint = (
        normalized.get("status") == "Compressed"
        or compressed_size > 0
        or int(normalized.get("compressed_file_count", 0) or 0) > 0
        or bool(normalized.get("compression_algorithm", ""))
    )
    if compressed_hint and compressed_size > 0:
        if size > 0 and compressed_size > size:
            normalized["original_size"] = max(original_size, manifest_size, compressed_size)
            normalized["compressed_size"] = size
            normalized["size"] = max(normalized["original_size"], manifest_size)
        elif original_size <= 0:
            normalized["original_size"] = max(size, manifest_size, compressed_size)
        else:
            normalized["original_size"] = max(original_size, manifest_size, compressed_size)

    if PYDANTIC_AVAILABLE:
        try:
            model = GameEntryModel(**normalized)
            normalized = _safe_model_dump(model)
        except ValidationError as exc:
            LOGGER.warning("game_entry_validation_failed", error=str(exc), game=normalized.get("name", "Unknown"))
        except Exception as exc:
            LOGGER.warning("game_entry_validation_error", error=str(exc), game=normalized.get("name", "Unknown"))
    return normalized


def _normalized_path(value):
    raw = str(value or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return os.path.normcase(os.path.abspath(raw))
    except Exception:
        return ""


def _normalized_id(value):
    return str(value or "").strip().lower()


FALLBACK_SOURCES = {"detected folder", "manual folder", "manual"}


def _normalized_name(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return "".join(ch for ch in text if ch.isalnum())


def _is_fallback_source(game):
    source = str((game or {}).get("source", "") or "").strip().lower()
    return source in FALLBACK_SOURCES


def _is_store_preferred_candidate(game):
                                                                                       
    return not _is_fallback_source(game) and is_store_game_installed(game)


def _merge_by_source_preference(existing, incoming):
    existing_is_fallback = _is_fallback_source(existing)
    incoming_is_fallback = _is_fallback_source(incoming)

    if existing_is_fallback and not incoming_is_fallback:
        return _merge_game_entries(existing, incoming)
    if incoming_is_fallback and not existing_is_fallback:
        return _merge_game_entries(incoming, existing)
    return _merge_game_entries(existing, incoming)


def _merge_game_entries(base, incoming):
    merged = dict(base)
    incoming_norm = normalize_game_entry(incoming)

                                                            
    if incoming_norm.get("path"):
        merged["path"] = incoming_norm.get("path")
    if incoming_norm.get("appid"):
        merged["appid"] = incoming_norm.get("appid")
    if incoming_norm.get("source"):
        merged["source"] = incoming_norm.get("source")
    if incoming_norm.get("name"):
        merged["name"] = incoming_norm.get("name")
    if incoming_norm.get("exe_path"):
        merged["exe_path"] = incoming_norm.get("exe_path")

                                          
    for key in ("size", "original_size", "manifest_size", "compressed_size", "compressed_file_count", "file_count", "scan_progress"):
        merged[key] = max(int(merged.get(key, 0) or 0), int(incoming_norm.get(key, 0) or 0))

    if not merged.get("poster") and incoming_norm.get("poster"):
        merged["poster"] = incoming_norm.get("poster")
    if merged.get("poster"):
        merged["poster_status"] = "Ready"
    else:
        merged["poster_status"] = incoming_norm.get("poster_status", merged.get("poster_status", "Queued"))

    if incoming_norm.get("compression_algorithm"):
        merged["compression_algorithm"] = incoming_norm.get("compression_algorithm")
    if incoming_norm.get("status") and merged.get("status", "Queued") in {"Queued", "Unknown"}:
        merged["status"] = incoming_norm.get("status")
    if incoming_norm.get("size_source") and merged.get("size_source", "Unknown") == "Unknown":
        merged["size_source"] = incoming_norm.get("size_source")

    if int(merged.get("compressed_size", 0) or 0) < 0:
        merged["compressed_size"] = 0

    return normalize_game_entry(merged)


def dedupe_games(games):
    deduped = []

    for raw_game in games or []:
        if not isinstance(raw_game, dict):
            continue
        game = normalize_game_entry(raw_game)
        game_path = _normalized_path(game.get("path", ""))
        game_appid = _normalized_id(game.get("appid", ""))
        game_exe = _normalized_path(game.get("exe_path", ""))

        match_index = None
        for idx, existing in enumerate(deduped):
            existing_path = _normalized_path(existing.get("path", ""))
            existing_appid = _normalized_id(existing.get("appid", ""))
            existing_exe = _normalized_path(existing.get("exe_path", ""))

            path_match = bool(game_path and existing_path and game_path == existing_path)
            appid_match = bool(game_appid and existing_appid and game_appid == existing_appid)
            exe_match = bool(game_exe and existing_exe and game_exe == existing_exe)

            if path_match or appid_match or exe_match:
                match_index = idx
                break

        if match_index is None:
            deduped.append(game)
        else:
            deduped[match_index] = _merge_by_source_preference(deduped[match_index], game)

                            
                                                                                               
    by_name_store = {}
    for index, game in enumerate(deduped):
        key = _normalized_name(game.get("name", ""))
        if not key:
            continue
        if _is_store_preferred_candidate(game):
            by_name_store[key] = index

    if by_name_store:
        filtered = []
        for game in deduped:
            key = _normalized_name(game.get("name", ""))
            if key and key in by_name_store and _is_fallback_source(game):
                continue
            filtered.append(game)
        deduped = filtered

    return deduped


def is_game_compressed(game):
    return (
        game.get("status") == "Compressed"
        or int(game.get("compressed_size", 0) or 0) > 0
        or int(game.get("compressed_file_count", 0) or 0) > 0
        or bool(game.get("compression_algorithm", ""))
    )


def original_game_size(game):
    size = int(game.get("size", 0) or 0)
    original_size = int(game.get("original_size", 0) or 0)
    manifest_size = int(game.get("manifest_size", 0) or 0)
    compressed_size = int(game.get("compressed_size", 0) or 0)
    if is_game_compressed(game):
        return max(original_size, size, manifest_size, compressed_size)
    return max(size, manifest_size, original_size)


def background_game_key(game):
    path = game.get("path", "")
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(path))


def background_saved_bytes(game):
    size = original_game_size(game)
    compressed_size = int(game.get("compressed_size", 0) or 0)
    if size <= 0 or compressed_size <= 0:
        return 0
    return max(0, size - compressed_size)


def background_is_game_checked(game, selection_mode, selected_paths):
    if selection_mode == "all":
        return True
    return background_game_key(game) in selected_paths


def background_is_decompress_checked(game, decompress_selected_paths):
    return background_game_key(game) in decompress_selected_paths


def background_compress_candidates(games, path_allowed_fn):
    candidates = []
    for index, game in enumerate(games):
        if is_game_compressed(game):
            continue
        ok, _ = path_allowed_fn(game.get("path", ""))
        if not ok:
            continue
        candidates.append((index, game))
    return candidates


def background_decompress_candidates(games, path_allowed_fn):
    candidates = []
    for index, game in enumerate(games):
        ok, _ = path_allowed_fn(game.get("path", ""))
        if ok:
            candidates.append((index, game))
    return candidates


def saved_game_is_installed(game):
    return is_store_game_installed(game)


def prune_uninstalled_games(games, installed_fn=saved_game_is_installed):
    kept = [game for game in games if installed_fn(game)]
    removed = len(games) - len(kept)
    return kept, removed


def load_games(data_file=DATA_FILE):
    if not os.path.exists(data_file):
        return []
    try:
        with open(data_file, "r", encoding="utf-8-sig") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            return []
        normalized = [normalize_game_entry(game) for game in loaded if isinstance(game, dict)]
        return dedupe_games(normalized)
    except Exception:
        return []


def save_games(games, data_file=DATA_FILE):
    parent = os.path.dirname(data_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=2)


def add_or_update_game(games, game, path_allowed_fn=safe_path):
    path = os.path.abspath(str(game.get("path", "") or "").strip().strip('"'))
    if not path or path == os.path.abspath(""):
        return False
    ok, _ = path_allowed_fn(path)
    if not ok:
        return False

    incoming = normalize_game_entry(game)
    incoming["path"] = path
    incoming_appid = _normalized_id(incoming.get("appid", ""))
    incoming_exe = _normalized_path(incoming.get("exe_path", ""))
    incoming_name = _normalized_name(incoming.get("name", ""))

                           
                                                                                                       
                                                                                                       
    if incoming_name:
        if _is_fallback_source(incoming):
            for existing in games:
                if _normalized_name(existing.get("name", "")) != incoming_name:
                    continue
                if _is_store_preferred_candidate(existing):
                    return False
        else:
            for existing in list(games):
                if (
                    _normalized_name(existing.get("name", "")) == incoming_name
                    and _is_fallback_source(existing)
                ):
                    incoming = _merge_game_entries(existing, incoming)
            games[:] = [
                existing for existing in games
                if not (
                    _normalized_name(existing.get("name", "")) == incoming_name
                    and _is_fallback_source(existing)
                )
            ]

    for existing in games:
        existing_path = _normalized_path(existing.get("path", ""))
        existing_appid = _normalized_id(existing.get("appid", ""))
        existing_exe = _normalized_path(existing.get("exe_path", ""))

        path_match = bool(existing_path and existing_path == _normalized_path(path))
        appid_match = bool(incoming_appid and existing_appid and incoming_appid == existing_appid)
        exe_match = bool(incoming_exe and existing_exe and incoming_exe == existing_exe)
        if not (path_match or appid_match or exe_match):
            continue

        preferred = _merge_by_source_preference(existing, incoming)
        existing.clear()
        existing.update(preferred)
        existing.setdefault("compressed_size", 0)
        existing.setdefault("compressed_file_count", 0)
        existing.setdefault("compression_algorithm", "")
        if int(existing.get("compressed_size", 0) or 0) < 0:
            existing["compressed_size"] = 0

        incoming_manifest_size = int(incoming.get("manifest_size", 0) or 0)
        if incoming_manifest_size:
            source = incoming.get("source", existing.get("source", "Store"))
            existing_size = int(existing.get("size", 0) or 0)
            existing_compressed_size = int(existing.get("compressed_size", 0) or 0)

                                                                                 
                                                                             
                                                                                
                                                                  
            if existing_size <= 0 or incoming_manifest_size >= max(existing_size, existing_compressed_size):
                existing["size"] = incoming_manifest_size
                existing["status"] = f"{source} Size"
                existing["size_source"] = f"{source} manifest"
            else:
                existing["size"] = max(existing_size, existing_compressed_size)
                existing["size_source"] = existing.get("size_source", "Folder scan") or "Folder scan"

            existing["manifest_size"] = max(int(existing.get("manifest_size", 0) or 0), incoming_manifest_size)
            existing["scan_progress"] = 100

        if not existing.get("poster"):
            existing["poster"] = incoming.get("poster", "")
            existing["poster_status"] = incoming.get("poster_status", "Queued")

        return False

    games.append(incoming)
    return True
