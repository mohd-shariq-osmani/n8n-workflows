#!/usr/bin/env python3
"""
Media Dispatcher for Radarr and Sonarr
Extracts IMDb links/IDs, identifies if Movie or TV Show (or Anime),
and adds to Radarr or Sonarr with automated hard drive folder organization.
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

RADARR_HOST = os.getenv("RADARR_HOST", DEFAULT_RADARR_HOST)
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "ebd830d1dbd34d299e45ad204ea33a23")
RADARR_ROOT_FOLDER = os.getenv("RADARR_ROOT_FOLDER", "/Volumes/HDD 4TB/Media Server/Movies")
RADARR_QUALITY_PROFILE_ID = int(os.getenv("RADARR_QUALITY_PROFILE_ID", "1"))

SONARR_HOST = os.getenv("SONARR_HOST", DEFAULT_SONARR_HOST)
SONARR_API_KEY = os.getenv("SONARR_API_KEY", "71f36ff7d42f46ffaef9d8ca8752670b")
SONARR_TV_ROOT_FOLDER = os.getenv("SONARR_TV_ROOT_FOLDER", "/Volumes/HDD 4TB/Media Server/TV Shows")
SONARR_ANIME_ROOT_FOLDER = os.getenv("SONARR_ANIME_ROOT_FOLDER", "/Volumes/HDD 4TB/Media Server/Anime")
SONARR_QUALITY_PROFILE_ID = int(os.getenv("SONARR_QUALITY_PROFILE_ID", "1"))

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
                msg = err_json[0].get("errorMessage", str(err_json))
            elif isinstance(err_json, dict):
                msg = err_json.get("message") or err_json.get("error") or str(err_json)
            else:
                msg = str(err_json)
        except Exception:
            msg = err_body or str(e)
        raise RuntimeError(f"HTTP {e.code}: {msg}")
    except Exception as e:
        raise RuntimeError(f"Request failed: {str(e)}")

def extract_imdb_id(text):
    """Extracts IMDb ID (tt...) from text, URL, or raw string."""
    if not text:
        return None
    match = re.search(r"\b(tt\d{7,10})\b", text)
    if match:
        return match.group(1)
    url_match = re.search(r"imdb\.com/title/(tt\d+)", text, re.IGNORECASE)
    if url_match:
        return url_match.group(1)
    return None

def lookup_radarr(imdb_id):
    """Look up a movie in Radarr by IMDb ID."""
    url = f"{RADARR_HOST}/api/v3/movie/lookup?term=imdb%3A{imdb_id}"
    try:
        results = api_request(url, RADARR_API_KEY, timeout=8)
        if isinstance(results, list) and len(results) > 0:
            for item in results:
                if item.get("imdbId") == imdb_id or str(item.get("imdbId", "")).lower() == imdb_id.lower():
                    return item
            return results[0]
    except Exception:
        pass
    return None

def lookup_sonarr(imdb_id):
    """Look up a series in Sonarr by IMDb ID."""
    url = f"{SONARR_HOST}/api/v3/series/lookup?term=imdb%3A{imdb_id}"
    try:
        results = api_request(url, SONARR_API_KEY, timeout=8)
        if isinstance(results, list) and len(results) > 0:
            for item in results:
                if item.get("imdbId") == imdb_id or str(item.get("imdbId", "")).lower() == imdb_id.lower():
                    return item
            return results[0]
    except Exception:
        pass
    return None

def get_poster_url(images):
    """Extract poster image URL from Radarr/Sonarr image list."""
    if not images or not isinstance(images, list):
        return None
    for img in images:
        if img.get("coverType") == "poster":
            return img.get("remoteUrl") or img.get("url")
    return None

def process_imdb_item(text_or_id):
    """Main processing logic for adding IMDb items to Radarr or Sonarr."""
    imdb_id = extract_imdb_id(text_or_id)
    if not imdb_id:
        return {
            "success": False,
            "error": "No valid IMDb ID (e.g. tt1234567) found in the message.",
            "input": text_or_id
        }

    imdb_url = f"https://www.imdb.com/title/{imdb_id}/"

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_sonarr = executor.submit(lookup_sonarr, imdb_id)
        future_radarr = executor.submit(lookup_radarr, imdb_id)

        sonarr_item = future_sonarr.result()
        radarr_item = future_radarr.result()

    if radarr_item and not sonarr_item:
        return add_to_radarr(radarr_item, imdb_url)
    elif sonarr_item and not radarr_item:
        return add_to_sonarr(sonarr_item, imdb_url)
    elif radarr_item and sonarr_item:
        if sonarr_item.get("seasons") and len(sonarr_item.get("seasons", [])) > 0:
            return add_to_sonarr(sonarr_item, imdb_url)
        else:
            return add_to_radarr(radarr_item, imdb_url)
    else:
        return {
            "success": False,
            "error": f"Could not find any Movie or TV Show matching IMDb ID '{imdb_id}' in Radarr or Sonarr.",
            "imdbId": imdb_id,
            "imdbUrl": imdb_url
        }

def add_to_radarr(movie, imdb_url):
    """Add a movie to Radarr or trigger search if already present."""
    title = movie.get("title", "Unknown Movie")
    year = movie.get("year", "")
    tmdb_id = movie.get("tmdbId")
    poster = get_poster_url(movie.get("images", []))
    overview = movie.get("overview", "")

    # Check if movie already exists in Radarr
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
            f"> 🔍 **Status:** Automated download search triggered via Prowlarr/qBittorrent."
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
            f"> 🔍 **Status:** Automated search initiated via Prowlarr/qBittorrent."
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

def add_to_sonarr(series, imdb_url):
    """Add a TV series / anime to Sonarr or trigger search if already present."""
    title = series.get("title", "Unknown Series")
    year = series.get("year", "")
    tvdb_id = series.get("tvdbId")
    genres = series.get("genres", [])
    series_type = series.get("seriesType", "standard")
    poster = get_poster_url(series.get("images", []))
    overview = series.get("overview", "")

    is_anime = any("anime" in str(g).lower() for g in genres) or series_type == "anime"
    root_folder = SONARR_ANIME_ROOT_FOLDER if is_anime else SONARR_TV_ROOT_FOLDER
    final_series_type = "anime" if is_anime else (series_type or "standard")
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

    if series_id and series_id > 0:
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
            f"> 🔍 **Status:** Automated episode search triggered via Prowlarr/qBittorrent."
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
            f"> 🔍 **Status:** Automated episode search initiated via Prowlarr/qBittorrent."
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
