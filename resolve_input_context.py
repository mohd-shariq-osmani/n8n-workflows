#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.parse
import re
import unicodedata
from bs4 import BeautifulSoup

def get_best_imdb_match(query):
    if not query or len(query.strip()) < 2:
        return None, ""
    
    clean_query = unicodedata.normalize('NFKD', query).strip()
    variations = [
        clean_query,
        clean_query.replace('are', 're').replace("'", ""),
        re.sub(r'[^a-zA-Z0-9\s]', '', clean_query)
    ]
    
    candidates = []
    for var in variations:
        clean = var.strip().replace(' ', '_').lower()
        if not clean or clean in ["recipe", "workout", "routine", "exercise", "github", "repo"]:
            continue
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{urllib.parse.quote(clean)}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for it in data.get('d', []):
                    if it.get('id', '').startswith('tt'):
                        candidates.append(it)
        except Exception:
            pass

    if not candidates:
        return None, ""

    def score(it):
        has_year = 1 if it.get('y') else 0
        rank = it.get('rank', 999999)
        q_type = it.get('q', '')
        is_primary = 1 if q_type in ['feature', 'TV series', 'TV mini-series', 'movie'] else 0
        return (-has_year, -is_primary, rank)

    candidates.sort(key=score)
    best = candidates[0]
    title_str = f"{best.get('l')} ({best.get('y')})" if best.get('y') else best.get('l')
    return title_str, f"https://www.imdb.com/title/{best.get('id')}/"

def search_github_repo_bs4(query):
    if not query or len(query.strip()) < 3:
        return ""
    try:
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": f"{query} github"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": "https://html.duckduckgo.com/"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            soup = BeautifulSoup(resp.read().decode("utf-8", errors="ignore"), "html.parser")
            for a in soup.find_all("a", class_="result__snippet") + soup.find_all("a", class_="result__url"):
                href = a.get("href", "") or a.get_text()
                m = re.search(r'(https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)', href)
                if m:
                    u = m.group(1).replace("http://", "https://")
                    if not any(b in u.lower() for b in ["/features", "/pricing", "/about", "/collections", "/trending", "/topics", "/sponsors", "/login"]):
                        return u
    except Exception:
        pass
    return ""

def resolve_context(raw_text):
    text = raw_text.strip()
    result = {
        "title": "",
        "imdbUrl": "",
        "githubUrl": "",
        "suggestedCategory": "",
        "contextNotes": ""
    }

    if not text:
        return result

    lower = text.lower()

    # 1. Tech & Project detection
    project_keywords = ["github", "repo", "library", "framework", "software", "sdk", "api", "npm", "pip", "developer tool", "open source", "workstation", "orchestrator", "ai agent", "coding", "terminal"]
    if any(k in lower for k in project_keywords) or "ai" in lower.split():
        result["suggestedCategory"] = "project"
        gh = search_github_repo_bs4(text)
        if gh:
            result["githubUrl"] = gh

    # 2. Recipe detection
    recipe_keywords = ["recipe", "ingredients", "cook", "bake", "grams", "tbsp", "tsp", "tablespoon", "pasta", "curry", "chicken", "salad", "cake", "sauce", "pan", "skillet", "oven", "boil"]
    if any(k in lower for k in recipe_keywords) and not result["suggestedCategory"]:
        result["suggestedCategory"] = "recipe"

    # 3. Workout detection
    workout_keywords = ["workout", "routine", "exercise", "sets", "reps", "bench press", "squat", "deadlift", "dumbbells", "bicep", "tricep", "chest", "back", "legs", "hypertrophy", "calisthenics", "mobility", "cardio", "push pull legs"]
    if any(k in lower for k in workout_keywords) and not result["suggestedCategory"]:
        result["suggestedCategory"] = "workout"

    # 4. Anime / Manhwa / Manga detection
    anime_keywords = ["anime", "manga", "manhwa", "manhua", "webtoon", "donghua", "light novel", "otaku", "crunchyroll"]
    if any(k in lower for k in anime_keywords) and not result["suggestedCategory"]:
        result["suggestedCategory"] = "anime"
        title, imdb_url = get_best_imdb_match(re.sub(r'(anime|manhwa|manga|manhua|webtoon|donghua)', '', text, flags=re.IGNORECASE).strip())
        if imdb_url:
            result["title"] = title
            result["imdbUrl"] = imdb_url

    # 5. Movie / TV Show detection
    if not result["suggestedCategory"]:
        title, imdb_url = get_best_imdb_match(text)
        if imdb_url:
            result["title"] = title
            result["imdbUrl"] = imdb_url
            result["suggestedCategory"] = "media"

    return result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query_input = " ".join(sys.argv[1:])
        res = resolve_context(query_input)
        print(json.dumps(res))
    else:
        print(json.dumps({}))
