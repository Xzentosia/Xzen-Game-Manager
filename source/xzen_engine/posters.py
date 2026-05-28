import os

import re
import shutil
import struct
from urllib.parse import quote

import requests

from .constants import POSTER_CACHE_DIR, STEAMGRIDDB_API_KEY

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_COLOR_CHUNKS = {b"cHRM", b"gAMA", b"iCCP", b"sRGB"}
MIN_POSTER_RATIO = 0.55
MAX_POSTER_RATIO = 0.78


def strip_png_color_chunks(data):
    if not data.startswith(PNG_SIGNATURE):
        return data, False

    output = bytearray(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    changed = False

    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_start = offset
        chunk_type = data[offset + 4:offset + 8]
        chunk_end = offset + 12 + length

        if chunk_end > len(data):
            return data, False

        if chunk_type in PNG_COLOR_CHUNKS:
            changed = True
        else:
            output.extend(data[chunk_start:chunk_end])

        offset = chunk_end
        if chunk_type == b"IEND":
            break

    return bytes(output), changed


def sanitize_png_file(path, target_base=None):
    if not path or not str(path).lower().endswith(".png") or not os.path.exists(path):
        return path

    try:
        with open(path, "rb") as f:
            original = f.read()
        cleaned, changed = strip_png_color_chunks(original)
        if not changed:
            return path

        target = path if target_base is None else target_base + ".png"
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(cleaned)
        return target
    except Exception:
        return path


def jpeg_dimensions(data):
    if not data.startswith(b"\xff\xd8"):
        return None

    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue

        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            return None

        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            return None

        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(data[offset + 3:offset + 5], "big")
            width = int.from_bytes(data[offset + 5:offset + 7], "big")
            return width, height

        offset += length

    return None


def webp_dimensions(data):
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None

    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height

    if chunk == b"VP8 " and len(data) >= 30:
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height

    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height

    return None


def image_dimensions(path):
    try:
        with open(path, "rb") as f:
            data = f.read(512 * 1024)
    except Exception:
        return None

    if data.startswith(PNG_SIGNATURE) and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

    if data.startswith(b"\xff\xd8"):
        return jpeg_dimensions(data)

    if data.startswith(b"RIFF"):
        return webp_dimensions(data)

    return None


def is_portrait_size(width, height):
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    return height > width and MIN_POSTER_RATIO <= ratio <= MAX_POSTER_RATIO


def is_portrait_poster_file(path):
    dimensions = image_dimensions(path)
    if not dimensions:
        return True
    return is_portrait_size(*dimensions)


def cache_local_poster(path, target_base):
    if not path or not os.path.exists(path):
        return ""

    ext = os.path.splitext(path)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        return path

    if not is_portrait_poster_file(path):
        return ""

    try:
        os.makedirs(os.path.dirname(target_base), exist_ok=True)
        if ext == ".png":
            sanitized = sanitize_png_file(path, target_base)
            if sanitized and os.path.exists(sanitized):
                return sanitized

        target = target_base + ext
        shutil.copy2(path, target)
        return target
    except Exception:
        return path


def find_local_steam_poster(steam_path, appid):
    if not steam_path or not appid:
        return ""

    cache = os.path.join(steam_path, "appcache", "librarycache")
    names = [
        f"{appid}_library_600x900.jpg", f"{appid}_library_600x900.png", f"{appid}_library_600x900.webp",
    ]

    for name in names:
        path = os.path.join(cache, name)
        if os.path.exists(path) and is_portrait_poster_file(path):
            return path

    if os.path.exists(cache):
        for file in os.listdir(cache):
            lower = file.lower()
            if lower.startswith(str(appid).lower()) and lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
                path = os.path.join(cache, file)
                if is_portrait_poster_file(path):
                    return path

    return ""


def image_extension_from_response(url, response):
    content_type = response.headers.get("Content-Type", "").lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"

    lower = url.lower().split("?")[0]
    if lower.endswith(".png"):
        return ".png"
    if lower.endswith(".webp"):
        return ".webp"
    if lower.endswith(".jpeg"):
        return ".jpg"
    if lower.endswith(".jpg"):
        return ".jpg"
    return ".jpg"


def download_image(url, target_base, auth_key=None):
    headers = {"User-Agent": "Mozilla/5.0 XzenGameCompressor/1.0"}
    if auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"

    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200 and len(response.content) > 1000:
            ext = image_extension_from_response(url, response)
            target = target_base + ext
            with open(target, "wb") as f:
                f.write(response.content)
            if ext == ".png":
                target = sanitize_png_file(target)
            if not is_portrait_poster_file(target):
                try:
                    os.remove(target)
                except Exception:
                    pass
                return ""
            return target
    except Exception:
        pass

    return ""


def download_file(url, target, auth_key=None):
    headers = {"User-Agent": "Mozilla/5.0 XzenGameCompressor/1.0"}
    if auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"

    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200 and len(response.content) > 1000:
            with open(target, "wb") as f:
                f.write(response.content)
            return target
    except Exception:
        pass

    return ""


def cached_image_for_prefix(prefix):
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = prefix + ext
        if os.path.exists(path):
            if ext == ".png":
                path = sanitize_png_file(path)
            if is_portrait_poster_file(path):
                return path
    return ""


def safe_cache_name(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "_", value)
    return value.strip("._-")[:80] or "game"


def poster_query_variants(name):
    raw = str(name or "").strip()
    if not raw:
        return []

    variants = []

    def add(value):
        value = re.sub(r"\s+", " ", str(value or "")).strip(" -_:")
        if value and value.lower() not in [item.lower() for item in variants]:
            variants.append(value)

    add(raw)
    add(re.sub(r"[™®©]", "", raw))
    add(re.sub(r"\([^)]*\)|\[[^]]*\]", " ", raw))
    add(re.split(r"\s*[:|-]\s*", raw, maxsplit=1)[0])
    add(re.sub(r"\b(launcher|content|edition|deluxe|ultimate|standard|complete|definitive|bundle|dlc)\b", " ", raw, flags=re.IGNORECASE))
    without_stay_human = re.sub(r"\bstay human\b", "", raw, flags=re.IGNORECASE)
    add(without_stay_human)
    add(re.split(r"\s*[:|-]\s*", without_stay_human, maxsplit=1)[0])

    if "minecraft" in raw.lower():
        add("Minecraft")

    return variants[:8]


def poster_score(item):
    width = int(item.get("width", 0) or 0)
    height = int(item.get("height", 0) or 0)
    if not is_portrait_size(width, height):
        return 0
    ratio = width / height
    pixels = width * height
    portrait_bonus = 2_000_000 if 0.55 <= ratio <= 0.75 else 0
    exact_600_900_bonus = 500_000 if width == 600 and height == 900 else 0
    return pixels + portrait_bonus + exact_600_900_bonus


def download_best_steamgriddb_grid(items, cached_prefix):
    if not items:
        return ""

    candidates = [item for item in items if poster_score(item) > 0]
    for item in sorted(candidates, key=poster_score, reverse=True):
        image_url = item.get("url", "")
        if not image_url:
            continue
        result = download_image(image_url, cached_prefix, STEAMGRIDDB_API_KEY)
        if result:
            return result
    return ""


def fetch_steamgriddb_poster(appid):
    if not appid or not STEAMGRIDDB_API_KEY:
        return ""

    os.makedirs(POSTER_CACHE_DIR, exist_ok=True)
    cached_prefix = os.path.join(POSTER_CACHE_DIR, f"{appid}_sgdb_best")
    cached = cached_image_for_prefix(cached_prefix)
    if cached:
        return cached

    api_url = (
        f"https://www.steamgriddb.com/api/v2/grids/steam/{appid}"
        "?types=static"
        "&nsfw=false"
        "&humor=false"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 XzenGameCompressor/1.0",
        "Authorization": f"Bearer {STEAMGRIDDB_API_KEY}",
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=20)
        if response.status_code != 200:
            return ""

        data = response.json()
        items = data.get("data", [])
        if not items:
            return ""

        return download_best_steamgriddb_grid(items, cached_prefix)
    except Exception:
        pass

    return ""


def fetch_steamgriddb_poster_by_query(query, source="", cache_label=""):
    if not query or not STEAMGRIDDB_API_KEY:
        return ""

    os.makedirs(POSTER_CACHE_DIR, exist_ok=True)
    label = cache_label or query
    cached_prefix = os.path.join(POSTER_CACHE_DIR, f"{safe_cache_name(f'{source}_{label}')}_sgdb_search")
    cached = cached_image_for_prefix(cached_prefix)
    if cached:
        return cached

    headers = {
        "User-Agent": "Mozilla/5.0 XzenGameCompressor/1.0",
        "Authorization": f"Bearer {STEAMGRIDDB_API_KEY}",
    }

    try:
        search_url = f"https://www.steamgriddb.com/api/v2/search/autocomplete/{quote(str(query))}"
        response = requests.get(search_url, headers=headers, timeout=20)
        if response.status_code != 200:
            return ""

        results = response.json().get("data", [])
        if not results:
            return ""

        exact_name = str(query).strip().lower()
        best_match = results[0]
        for item in results:
            if str(item.get("name", "")).strip().lower() == exact_name:
                best_match = item
                break

        game_id = best_match.get("id")
        if not game_id:
            return ""

        grids_url = (
            f"https://www.steamgriddb.com/api/v2/grids/game/{game_id}"
            "?types=static"
            "&nsfw=false"
            "&humor=false"
        )
        grids_response = requests.get(grids_url, headers=headers, timeout=20)
        if grids_response.status_code != 200:
            return ""

        return download_best_steamgriddb_grid(grids_response.json().get("data", []), cached_prefix)
    except Exception:
        return ""


def fetch_steamgriddb_poster_by_name(name, source=""):
    for query in poster_query_variants(name):
        result = fetch_steamgriddb_poster_by_query(query, source, cache_label=name)
        if result:
            return result
    return ""


def fetch_steam_appid_by_name(name):
    for query in poster_query_variants(name):
        try:
            url = f"https://store.steampowered.com/api/storesearch/?term={quote(query)}&cc=us&l=en"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 XzenGameCompressor/1.0"}, timeout=12)
            if response.status_code != 200:
                continue

            items = response.json().get("items", [])
            if not items:
                continue

            exact = query.strip().lower()
            best = items[0]
            for item in items:
                if str(item.get("name", "")).strip().lower() == exact:
                    best = item
                    break

            appid = str(best.get("id", "") or "").strip()
            if appid.isdigit():
                return appid
        except Exception:
            pass

    return ""


def fetch_store_api_image(appid, target_base):
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 XzenGameCompressor/1.0"}, timeout=12)
        if response.status_code != 200:
            return ""

        data = response.json()
        entry = data.get(str(appid), {})
        if not entry.get("success"):
            return ""

        info = entry.get("data", {})
        for image_url in [info.get("capsule_imagev5", ""), info.get("header_image", ""), info.get("capsule_image", "")]:
            if image_url:
                result = download_image(image_url, target_base)
                if result:
                    return result
    except Exception:
        pass

    return ""


def download_steam_poster(appid):
    if not appid:
        return ""

    os.makedirs(POSTER_CACHE_DIR, exist_ok=True)
    cached_prefix = os.path.join(POSTER_CACHE_DIR, f"{appid}_steam_best")
    cached = cached_image_for_prefix(cached_prefix)
    if cached:
        return cached

    urls = [
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
        f"https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg",
        f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/library_600x900.jpg",
    ]

    for url in urls:
        result = download_image(url, cached_prefix)
        if result:
            return result

    return ""


def get_poster_for_game(steam_path, appid, name="", source=""):
    appid = str(appid or "").strip()
    source = str(source or "").strip()

    if appid and (source == "Steam" or appid.isdigit()):
        sgdb = fetch_steamgriddb_poster(appid)
        if sgdb:
            return sgdb

        local = find_local_steam_poster(steam_path, appid)
        if local:
            local_prefix = os.path.join(POSTER_CACHE_DIR, f"{appid}_steam_local")
            return cache_local_poster(local, local_prefix)

        steam_poster = download_steam_poster(appid)
        if steam_poster:
            return steam_poster

    sgdb = fetch_steamgriddb_poster_by_name(name, source)
    if sgdb:
        return sgdb

    steam_appid = fetch_steam_appid_by_name(name)
    if steam_appid:
        return download_steam_poster(steam_appid)

    return ""

