#!/usr/bin/env python3
"""
Media Dispatcher for Radarr, Sonarr, and Jellyfin
Extracts IMDb links/IDs, identifies if Movie or TV Show (or Anime),
adds to Radarr or Sonarr with automated hard drive folder organization,
and triggers automatic Jellyfin library refresh.
"""

import sys
import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor

# Environment / Default Settings
DEFAULT_RADARR_HOST = "http://host.docker.internal:7878" if os.path.exists("/.dockerenv") else "http://localhost:7878"
DEFAULT_SONARR_HOST = "http://host.docker.internal:8989" if os.path.exists("/.dockerenv") else "http://localhost:8989"
DEFAULT_JELLYFIN_HOST = "http://host.docker.internal:8096" if os.path.exists("/.dockerenv") else "http://localhost:8096"

RADARR_HOST = os.getenv("RADARR_HOST", DEFAULT_RADARR_HOST)
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "ebd830d1dbd34d299e45ad204ea33a23")
RADARR_ROOT_FOLDER = os.getenv("RADARR_ROOT_FOLDER", "/Volumes/HDD 4TB/Media Server/Movies")
RADARR_QUALITY_PROFILE_ID = int(os.getenv("RADARR_QUALITY_PROFILE_ID", "1"))

SONARR_HOST = os.getenv("SONARR_HOST", DEFAULT_SONARR_HOST)
SONARR_API_KEY = os.getenv("SONARR_API_KEY", "71f36ff7d42f46ffaef9d8ca8752670b")
SONARR_TV_ROOT_FOLDER = os.getenv("SONARR_TV_ROOT_FOLDER", "/Volumes/HDD 4TB/Media Server/TV Shows")
SONARR_ANIME_ROOT_FOLDER = os.getenv("SONARR_ANIME_ROOT_FOLDER", "/Volumes/HDD 4TB/Media Server/Anime")
SONARR_QUALITY_PROFILE_ID = int(os.getenv("SONARR_QUALITY_PROFILE_ID", "1"))

JELLYFIN_HOST = os.getenv("JELLYFIN_HOST", DEFAULT_JELLYFIN_HOST)
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "jellyfin_26ef8f71a7e190e4d10e7134f70fb125")

def api_request(url, api_key, data=None, method="GET", timeout=8):
    """Performs an HTTP request to Radarr/Sonarr API."""
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            if isinstance(err_json, list) and len(err_json) > 0:
                err_msg = err_json[0].get("errorMessage", err_body)
            else:
                err_msg = err_json.get("message", err_body)
        except Exception:
            err_msg = err_body
        raise Exception(f"HTTP {e.code}: {err_msg}")
    except Exception as e:
        raise Exception(f"Request failed: {str(e)}")

def trigger_jellyfin_refresh():
    """Trigger library refresh in Jellyfin to scan for newly added/downloaded media."""
    try:
        req = urllib.request.Request(
            f"{JELLYFIN_HOST}/Library/Refresh",
            data=b"",
            headers={
                "X-Emby-Token": JELLYFIN_API_KEY,
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in [200, 204]
    except Exception:
        return False

def extract_imdb_id(text):
    """Extracts canonical tt-style IMDb ID from any text, URL, or payload."""
    if not text:
        return None
    match = re.search(r'tt\d{7,8}', text)
    if match:
        return match.group(0)
    match_url = re.search(r'imdb\.com/title/(tt\d+)', text)
    if match_url:
        return match_url.group(1)
    return None

def get_poster_url(images):
    if not images:
        return None
    for img in images:
        if img.get("coverType") in ["poster", "Poster", "headshot"]:
            return img.get("remoteUrl") or img.get("url")
    return images[0].get("remoteUrl") or images[0].get("url")

def lookup_radarr(imdb_id):
    try:
        url = f"{RADARR_HOST}/api/v3/movie/lookup/imdb?imdbId={imdb_id}"
        data = api_request(url, RADARR_API_KEY, timeout=6)
        if isinstance(data, dict) and data.get("title"):
            return data
    except Exception:
        pass
    return None

def lookup_sonarr(imdb_id):
    try:
        url = f"{SONARR_HOST}/api/v3/series/lookup?term=imdb:{imdb_id}"
        data = api_request(url, SONARR_API_KEY, timeout=6)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        elif isinstance(data, dict) and data.get("title"):
            return data
    except Exception:
        pass
    return None

def is_anime_series(series, input_data=""):
    """Robust multi-factor detection to determine if a show belongs in the Anime folder."""
    genres = [str(g).lower() for g in series.get("genres", [])]
    series_type = str(series.get("seriesType", "")).lower()
    lang = str(series.get("originalLanguage", {}).get("name", "")).lower()
    title = str(series.get("title", "")).lower()
    overview = str(series.get("overview", "")).lower()
    input_lower = str(input_data).lower()

    # 1. Direct channel or input hints
    if "anime-manhua" in input_lower or "anime" in input_lower or "manhwa" in input_lower or "manga" in input_lower:
        return True

    # 2. Genre or Type checks
    if any(g in ["anime", "animation", "donghua"] for g in genres) and (lang in ["japanese", "korean", "chinese"] or "anime" in genres):
        return True
    
    if "anime" in genres or series_type == "anime":
        return True

    # 3. Japanese / Asian Animation
    if lang == "japanese" and "animation" in genres:
        return True

    # 4. Keyword heuristics in title or synopsis
    anime_keywords = [
        "isekai", "reincarnat", "leveling", "jujutsu", "demon slayer", "titan",
        "naruto", "one piece", "bleach", "dragon ball", "shonen", "seinen",
        "cheat skill", "hunter", "manhwa", "manhua", "donghua", "gintama",
        "shadow", "slayer", "healer", "crunchyroll"
    ]
    if any(k in title for k in anime_keywords) or (any(k in overview for k in anime_keywords) and "animation" in genres):
        return True

    return False

def process_imdb_item(input_data):
    """Main routing logic: checks Radarr & Sonarr, adds item, and triggers Jellyfin scan."""
    imdb_id = extract_imdb_id(input_data)
    if not imdb_id:
        return {
            "success": False,
            "error": "No valid IMDb ID (e.g. tt1234567) found in the provided input.",
            "rawInput": input_data[:300]
        }

    imdb_url = f"https://www.imdb.com/title/{imdb_id}/"

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_radarr = executor.submit(lookup_radarr, imdb_id)
        future_sonarr = executor.submit(lookup_sonarr, imdb_id)
        radarr_movie = future_radarr.result()
        sonarr_series = future_sonarr.result()

    if radarr_movie and not sonarr_series:
        return add_to_radarr(radarr_movie, imdb_url)
    elif sonarr_series and not radarr_movie:
        return add_to_sonarr(sonarr_series, imdb_url, input_data)
    elif radarr_movie and sonarr_series:
        if is_anime_series(sonarr_series, input_data) or sonarr_series.get("episodeCount", 0) > 1:
            return add_to_sonarr(sonarr_series, imdb_url, input_data)
        else:
            return add_to_radarr(radarr_movie, imdb_url)
    else:
        return {
            "success": False,
            "error": f"Could not find any Movie or TV Show matching IMDb ID '{imdb_id}' in Radarr or Sonarr.",
            "imdbId": imdb_id,
            "imdbUrl": imdb_url
        }

def add_to_radarr(movie, imdb_url):
    """Add a movie to Radarr or trigger search if already present, then trigger Jellyfin refresh."""
    title = movie.get("title", "Unknown Movie")
    year = movie.get("year", "")
    tmdb_id = movie.get("tmdbId")
    poster = get_poster_url(movie.get("images", []))
    overview = movie.get("overview", "")

    movie_id = movie.get("id")
    if not movie_id or movie_id == 0:
        try:
            existing = api_request(f"{RADARR_HOST}/api/v3/movie", RADARR_API_KEY, timeout=5)
            for m in existing:
                if m.get("tmdbId") == tmdb_id or m.get("imdbId") == movie.get("imdbId"):
                    movie_id = m.get("id")
                    break
        except Exception:
            pass

    jellyfin_refreshed = trigger_jellyfin_refresh()

    if movie_id and movie_id > 0:
        try:
            api_request(
                f"{RADARR_HOST}/api/v3/command",
                RADARR_API_KEY,
                data={"name": "MoviesSearch", "movieIds": [movie_id]},
                method="POST",
                timeout=5
            )
            search_triggered = True
        except Exception:
            search_triggered = False

        msg = (
            f"🎬 **{title} ({year})** is already in your **Radarr** library.\n"
            f"> 📂 **Hard Drive Folder:** `{RADARR_ROOT_FOLDER}/{title} ({year})`\n"
            f"> 🔗 **IMDb:** {imdb_url}\n"
            f"> 🔍 **Status:** Automated download search triggered via Prowlarr/qBittorrent.\n"
            f"> 🍿 **Jellyfin:** Library scan triggered."
        )

        return {
            "success": True,
            "action": "already_exists",
            "service": "Radarr",
            "mediaType": "Movie",
            "title": title,
            "year": year,
            "imdbId": movie.get("imdbId"),
            "imdbUrl": imdb_url,
            "tmdbId": tmdb_id,
            "rootFolder": RADARR_ROOT_FOLDER,
            "posterUrl": poster,
            "overview": overview,
            "searchTriggered": search_triggered,
            "jellyfinRefreshed": jellyfin_refreshed,
            "message": msg
        }

    # Add new movie
    payload = {
        "title": title,
        "qualityProfileId": RADARR_QUALITY_PROFILE_ID,
        "titleSlug": movie.get("titleSlug"),
        "images": movie.get("images", []),
        "tmdbId": tmdb_id,
        "year": year,
        "rootFolderPath": RADARR_ROOT_FOLDER,
        "monitored": True,
        "addOptions": {
            "searchForMovie": True
        },
        "minimumAvailability": "announced"
    }

    try:
        res = api_request(f"{RADARR_HOST}/api/v3/movie", RADARR_API_KEY, data=payload, method="POST", timeout=10)
        msg = (
            f"🎬 Successfully added **{title} ({year})** to **Radarr**!\n"
            f"> 📂 **Hard Drive Folder:** `{RADARR_ROOT_FOLDER}/{title} ({year})`\n"
            f"> 🔗 **IMDb:** {imdb_url}\n"
            f"> 🔍 **Status:** Automated search initiated via Prowlarr/qBittorrent.\n"
            f"> 🍿 **Jellyfin:** Library scan triggered."
        )
        return {
            "success": True,
            "action": "added",
            "service": "Radarr",
            "mediaType": "Movie",
            "title": title,
            "year": year,
            "imdbId": movie.get("imdbId"),
            "imdbUrl": imdb_url,
            "tmdbId": tmdb_id,
            "rootFolder": RADARR_ROOT_FOLDER,
            "posterUrl": poster,
            "overview": overview,
            "searchTriggered": True,
            "jellyfinRefreshed": jellyfin_refreshed,
            "message": msg
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to add '{title}' to Radarr: {str(e)}",
            "service": "Radarr",
            "title": title,
            "imdbUrl": imdb_url
        }

def add_to_sonarr(series, imdb_url, input_data=""):
    """Add a TV series / anime to Sonarr or trigger search if already present, then trigger Jellyfin refresh."""
    title = series.get("title", "Unknown Series")
    year = series.get("year", "")
    tvdb_id = series.get("tvdbId")
    poster = get_poster_url(series.get("images", []))
    overview = series.get("overview", "")

    is_anime = is_anime_series(series, input_data)
    root_folder = SONARR_ANIME_ROOT_FOLDER if is_anime else SONARR_TV_ROOT_FOLDER
    final_series_type = "anime" if is_anime else (series.get("seriesType") or "standard")
    type_label = "Anime Series" if is_anime else "TV Show"

    series_id = series.get("id")
    if not series_id or series_id == 0:
        try:
            existing = api_request(f"{SONARR_HOST}/api/v3/series", SONARR_API_KEY, timeout=5)
            for s in existing:
                if s.get("tvdbId") == tvdb_id or s.get("imdbId") == series.get("imdbId"):
                    series_id = s.get("id")
                    break
        except Exception:
            pass

    jellyfin_refreshed = trigger_jellyfin_refresh()

    if series_id and series_id > 0:
        # Check if the existing series path needs to be moved/corrected
        try:
            cur_series = api_request(f"{SONARR_HOST}/api/v3/series/{series_id}", SONARR_API_KEY, timeout=5)
            cur_path = cur_series.get("path", "")
            if is_anime and "TV Shows" in cur_path:
                cur_series["path"] = f"{SONARR_ANIME_ROOT_FOLDER}/{title}"
                cur_series["rootFolderPath"] = SONARR_ANIME_ROOT_FOLDER
                cur_series["seriesType"] = "anime"
                api_request(f"{SONARR_HOST}/api/v3/series/{series_id}?moveFiles=true", SONARR_API_KEY, data=cur_series, method="PUT", timeout=8)
        except Exception:
            pass

        try:
            api_request(
                f"{SONARR_HOST}/api/v3/command",
                SONARR_API_KEY,
                data={"name": "SeriesSearch", "seriesId": series_id},
                method="POST",
                timeout=5
            )
            search_triggered = True
        except Exception:
            search_triggered = False

        msg = (
            f"📺 **{title} ({year})** is already in your **Sonarr** library ({type_label}).\n"
            f"> 📂 **Hard Drive Folder:** `{root_folder}/{title}`\n"
            f"> 🔗 **IMDb:** {imdb_url}\n"
            f"> 🔍 **Status:** Automated episode search triggered via Prowlarr/qBittorrent.\n"
            f"> 🍿 **Jellyfin:** Library scan triggered."
        )

        return {
            "success": True,
            "action": "already_exists",
            "service": "Sonarr",
            "mediaType": type_label,
            "title": title,
            "year": year,
            "imdbId": series.get("imdbId"),
            "imdbUrl": imdb_url,
            "tvdbId": tvdb_id,
            "rootFolder": root_folder,
            "posterUrl": poster,
            "overview": overview,
            "searchTriggered": search_triggered,
            "jellyfinRefreshed": jellyfin_refreshed,
            "message": msg
        }

    payload = {
        "title": title,
        "qualityProfileId": SONARR_QUALITY_PROFILE_ID,
        "titleSlug": series.get("titleSlug"),
        "images": series.get("images", []),
        "tvdbId": tvdb_id,
        "year": year,
        "rootFolderPath": root_folder,
        "monitored": True,
        "seasonFolder": True,
        "seriesType": final_series_type,
        "addOptions": {
            "searchForMissingEpisodes": True
        }
    }

    try:
        res = api_request(f"{SONARR_HOST}/api/v3/series", SONARR_API_KEY, data=payload, method="POST", timeout=10)
        msg = (
            f"📺 Successfully added **{title} ({year})** to **Sonarr** ({type_label})!\n"
            f"> 📂 **Hard Drive Folder:** `{root_folder}/{title}`\n"
            f"> 🔗 **IMDb:** {imdb_url}\n"
            f"> 🔍 **Status:** Automated episode search initiated via Prowlarr/qBittorrent.\n"
            f"> 🍿 **Jellyfin:** Library scan triggered."
        )
        return {
            "success": True,
            "action": "added",
            "service": "Sonarr",
            "mediaType": type_label,
            "title": title,
            "year": year,
            "imdbId": series.get("imdbId"),
            "imdbUrl": imdb_url,
            "tvdbId": tvdb_id,
            "rootFolder": root_folder,
            "posterUrl": poster,
            "overview": overview,
            "searchTriggered": True,
            "jellyfinRefreshed": jellyfin_refreshed,
            "message": msg
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to add '{title}' to Sonarr: {str(e)}",
            "service": "Sonarr",
            "title": title,
            "imdbUrl": imdb_url
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        input_text = sys.stdin.read()
    else:
        input_text = " ".join(sys.argv[1:])

    result = process_imdb_item(input_text.strip())
    print(json.dumps(result, indent=2))
