import os

from .app_state import background_game_key, background_saved_bytes, is_game_compressed


def build_game_detection_paths(games, is_exe_file):
    paths = []
    for game in games:
        game_path = game.get("path", "")
        if game_path:
            paths.append(game_path)

        exe_path = game.get("exe_path", "")
        if exe_path and is_exe_file(exe_path):
            paths.append(os.path.dirname(exe_path))

    return [path for path in paths if path]


def build_background_queue(
    games,
    selection_mode,
    selected_paths,
    decompress_selected_paths,
    path_allowed_fn,
):
    compress_candidates = []
    decompress_candidates = []
    skipped_invalid = 0
    skipped_unselected = 0
    skipped_decompress_unselected = 0

    for index, game in enumerate(games):
        key = background_game_key(game)
        ok, _ = path_allowed_fn(game.get("path", ""))
        if not ok:
            skipped_invalid += 1
            continue

        if is_game_compressed(game):
            if key not in decompress_selected_paths:
                skipped_decompress_unselected += 1
                continue
            decompress_candidates.append((index, background_saved_bytes(game)))
            continue

        if key in decompress_selected_paths:
            decompress_candidates.append((index, background_saved_bytes(game)))
            continue

        if selection_mode == "custom" and key not in selected_paths:
            skipped_unselected += 1
            continue

        size = int(game.get("size", 0) or game.get("manifest_size", 0) or 0)
        compress_candidates.append((index, size))

    small = sorted(compress_candidates, key=lambda item: item[1])
    large = []
    if len(small) > 4:
        split_at = max(1, int(len(small) * 0.75))
        large = small[split_at:]
        small = small[:split_at]

    ordered = []
    while small or large:
        for _ in range(4):
            if small:
                ordered.append(small.pop(0))
        if large:
            ordered.append(large.pop(0))

    decompress_ordered = sorted(decompress_candidates, key=lambda item: item[1], reverse=True)
    queue = [{"action": "decompress", "index": index} for index, _ in decompress_ordered]
    queue.extend({"action": "compress", "index": index} for index, _ in ordered)
    skipped = {
        "invalid": skipped_invalid,
        "unchecked_compress": skipped_unselected,
        "unchecked_decompress": skipped_decompress_unselected,
    }
    return queue, skipped
