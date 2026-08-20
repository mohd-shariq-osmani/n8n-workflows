#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.parse
import re
import unicodedata
from bs4 import BeautifulSoup

def get_imdb_meta_by_id(tt_id):
    if not tt_id:
        return None
    try:
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{tt_id}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for it in data.get("d", []):
                if it.get("id") == tt_id:
                    year = it.get("y")
                    title_str = f"{it.get('l')} ({year})" if year else it.get('l')
                    stars = it.get("s", "")
                    q_type = it.get("q", "Movie / TV Show")
                    img_url = it.get("i", {}).get("imageUrl", "")
                    
                    desc = f"{title_str} • Type: {q_type}"
                    if stars:
                        desc += f" • Starring: {stars}"
                        
                    return {
                        "title": title_str,
                        "cleanTitle": it.get("l"),
                        "year": year,
                        "type": q_type,
                        "stars": stars,
                        "caption": desc,
                        "imageUrl": img_url,
                        "imdbUrl": f"https://www.imdb.com/title/{tt_id}/"
                    }
    except Exception:
        pass
    return None

def lookup_imdb_precise(title_query):
    if not title_query or len(title_query.strip()) < 2:
        return None, ""
        
    tt_match = re.search(r'tt\d{7,8}', title_query)
    if tt_match:
        meta = get_imdb_meta_by_id(tt_match.group(0))
        if meta:
            return meta["title"], meta["imdbUrl"]

    norm = unicodedata.normalize('NFKD', title_query)
    year_match = re.search(r'\((\d{4})\)', norm)
    target_year = int(year_match.group(1)) if year_match else None
    
    clean = re.sub(r'[\#\*\_\(\)🎬🎌🏷️•\>\:\-]', ' ', norm)
    clean = re.sub(r'\b(20\d\d|19\d\d)\b', '', clean)
    clean = re.sub(r'\b(anime|manga|manhwa|manhua|webtoon|movie|series|tv|season|show|recommendation|complete series|hindi dubbed)\b', '', clean, flags=re.IGNORECASE)
    clean = ' '.join(clean.split()).strip()
    
    if len(clean) < 2:
        return None, ""
        
    variations = [
        clean,
        clean.replace(' ', '_'),
        re.sub(r'[^a-zA-Z0-9\s]', '', clean),
        re.sub(r'[^a-zA-Z0-9\s]', '', clean).replace(' ', '_')
    ]
    
    candidates = []
    seen_ids = set()
    for var in variations:
        q = var.strip().replace(' ', '_').lower()
        if not q:
            continue
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{urllib.parse.quote(q)}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for it in data.get('d', []):
                    item_id = it.get('id', '')
                    if item_id.startswith('tt') and item_id not in seen_ids:
                        candidates.append(it)
                        seen_ids.add(item_id)
        except Exception:
            pass
            
    if not candidates:
        return None, ""
        
    def score(it):
        item_title = it.get('l', '').lower().strip()
        query_lower = clean.lower()
        
        exact_match = 100 if item_title == query_lower else (50 if query_lower in item_title or item_title in query_lower else 0)
        
        item_year = it.get('y')
        year_score = 0
        if target_year and item_year:
            year_score = 40 if abs(item_year - target_year) <= 1 else -10
        elif item_year:
            year_score = 5

        q_type = it.get('q', '')
        is_primary = 20 if q_type in ['feature', 'TV series', 'TV mini-series', 'movie', 'tvSpecial'] else 0
        
        rank = it.get('rank', 999999)
        total_score = exact_match + year_score + is_primary
        return (-total_score, rank)

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

    # 1. Direct IMDb ID / Link Detection
    tt_match = re.search(r'tt\d{7,8}', text)
    if "imdb.com" in text.lower() or tt_match:
        tt_id = tt_match.group(0) if tt_match else ""
        meta = get_imdb_meta_by_id(tt_id)
        if meta:
            result["title"] = meta["title"]
            result["imdbUrl"] = meta["imdbUrl"]
            result["suggestedCategory"] = "media"
            return result

    lower = text.lower()

    # 2. Tech & Project detection
    project_keywords = ["github", "repo", "library", "framework", "software", "sdk", "api", "npm", "pip", "developer tool", "open source", "workstation", "orchestrator", "ai agent", "coding", "terminal"]
    if any(k in lower for k in project_keywords) or "ai" in lower.split():
        result["suggestedCategory"] = "project"
        gh = search_github_repo_bs4(text)
        if gh:
            result["githubUrl"] = gh

    # 3. Recipe detection
    recipe_keywords = ["recipe", "ingredients", "cook", "bake", "grams", "tbsp", "tsp", "tablespoon", "pasta", "curry", "chicken", "salad", "cake", "sauce", "pan", "skillet", "oven", "boil"]
    if any(k in lower for k in recipe_keywords) and not result["suggestedCategory"]:
        result["suggestedCategory"] = "recipe"

    # 4. Workout detection
    workout_keywords = ["workout", "routine", "exercise", "sets", "reps", "bench press", "squat", "deadlift", "dumbbells", "bicep", "tricep", "chest", "back", "legs", "hypertrophy", "calisthenics", "mobility", "cardio", "push pull legs"]
    if any(k in lower for k in workout_keywords) and not result["suggestedCategory"]:
        result["suggestedCategory"] = "workout"

    # 5. Anime / Manhwa / Manga detection
    anime_keywords = ["anime", "manga", "manhwa", "manhua", "webtoon", "donghua", "light novel", "otaku", "crunchyroll"]
    if any(k in lower for k in anime_keywords) and not result["suggestedCategory"]:
        result["suggestedCategory"] = "anime"
        title, imdb_url = lookup_imdb_precise(re.sub(r'(anime|manhwa|manga|manhua|webtoon|donghua)', '', text, flags=re.IGNORECASE).strip())
        if imdb_url:
            result["title"] = title
            result["imdbUrl"] = imdb_url

    # 6. Movie / TV Show detection
    if not result["suggestedCategory"]:
        title, imdb_url = lookup_imdb_precise(text)
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
