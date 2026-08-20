#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.parse
import re
import unicodedata
from bs4 import BeautifulSoup

ANIME_FRANCHISES = {
    'bleach', 'naruto', 'boruto', 'one piece', 'dragon ball', 'jujutsu kaisen', 'demon slayer',
    'kimetsu no yaiba', 'attack on titan', 'shingeki no kyojin', 'frieren', 'chainsaw man',
    'solo leveling', 'lookism', 'tower of god', 'god of high school', 'wind breaker', 'blue lock',
    'haikyuu', 'kuroko', 'baki', 'kengan ashura', 'berserk', 'evangelion', 'steins gate',
    'mushoku tensei', 'isekai', 'reincarnat', 'slime', 'konosuba', 'overlord', 'shield hero',
    'sword art online', 'death note', 'code geass', 'hunter x hunter', 'fullmetal alchemist',
    'vinland saga', 'tokyo ghoul', 'mob psycho', 'one punch man', 'my hero academia', 'boku no hero',
    'spy x family', 'dandadan', 'sakamoto days', 'kaiju no 8', 'hellsing', 'gintama', 'monster',
    'dr stone', 'black clover', 'fairy tail', 'fate', 'monogatari', 'bungo stray dogs',
    'classroom of the elite', 'horimiya', 'kaguya sama', 'oshi no ko', 'drifters', 'claymore',
    'parasyte', 'dororo', 'erased', 'psycho pass', 'akame ga kill', 'kill la kill', 'gurren lagann',
    'trigun', 'cowboy bebop', 'samurai champloo', 'yu yu hakusho', 'rurouni kenshin', 'inuyasha',
    'saint seiya', 'gundam', 'macross', 'initial d', 'hajime no ippo', 'slam dunk', 'gto',
    'sailor moon', 'cardcaptor sakura', 'pokemon', 'digimon', 'yu gi oh', 'jojo', 'bizarre adventure',
    'danganronpa', 'persona', 'nier automata', 'cyberpunk edgerunners', 'the beginning after the end',
    'omniscient reader', 'nanatsu no taizai', 'seven deadly sins', 'black butler', 'soul eater',
    'fire force', 'enen no shouboutai', 'blue exorcist', 'noragami', 'charlotte', 'angel beats',
    'clannad', 'your lie in april', 'anohana', 'violet evergarden', 'made in abyss', 'vinland',
    'the promised neverland', 'yakusoku no neverland', 'dr stone', 'beastars', 'banana fish',
    'danmachi', 'is it wrong to try to pick up girls in a dungeon', 'eminence in shadow',
    'the brilliant healer', 'cheat skill', 'shangri la frontier', 'undead unluck', 'mashle'
}

JAPANESE_VOICE_PATTERN = r'\b(Masakazu|Jun\'ya|Kikunosuke|Taito|Natsuki|Atsumi|Kana|Hiroshi|Kenjiro|Rie|Saori|Mamoru|Takehito|Megumi|Yuuki|Ayumu|Daiki|Yoshitsugu|Kaito|Nobunaga|Takahiro|Daisuke|Tomokazu|Yuki|Kenichi|Satoshi|Katsuyuki|Shinichiro|Takeo|Tatsuhisa|Kazuhiko|Showtaro|Tetsuya|Shouta|Koichi|Ryota|Yuma|Koki|Sora|Reina|Inori|Akari|Ayane|Aoi|Haruka|Yui|Maaya|Miyuki|Ai|Shizuka|Asami|Miku|Sumire|Hina|Manaka|Akari|Minami)\b'

def normalize_text(text):
    if not text:
        return ""
    norm = unicodedata.normalize('NFKD', text)
    clean = re.sub(r'[\#\*\_\(\)🎬🎌🏷️•\>\:\-\,\.\'\"]', ' ', norm)
    clean = re.sub(r'\b(20\d\d|19\d\d)\b', '', clean)
    clean = re.sub(r'\b(anime|manga|manhwa|manhua|webtoon|movie|series|tv|season|show|recommendation|complete series|hindi dubbed)\b', '', clean, flags=re.IGNORECASE)
    return ' '.join(clean.lower().split()).strip()

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
        return None, "", ""
        
    tt_match = re.search(r'tt\d{7,8}', title_query)
    if tt_match:
        meta = get_imdb_meta_by_id(tt_match.group(0))
        if meta:
            return meta["title"], meta["imdbUrl"], meta["stars"]

    year_match = re.search(r'\((\d{4})\)', title_query)
    target_year = int(year_match.group(1)) if year_match else None
    query_norm = normalize_text(title_query)
    
    if len(query_norm) < 2:
        return None, "", ""
        
    variations = [
        query_norm,
        query_norm.replace(' ', '_'),
        re.sub(r'[^a-zA-Z0-9\s]', '', query_norm),
        re.sub(r'[^a-zA-Z0-9\s]', '', query_norm).replace(' ', '_')
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
        return None, "", ""
        
    def score(it):
        item_title = it.get('l', '').strip()
        item_norm = normalize_text(item_title)
        
        # 1. Title match
        if item_norm == query_norm:
            title_score = 150
        elif query_norm in item_norm:
            title_score = 40
        elif item_norm in query_norm:
            title_score = 30
        else:
            title_score = 0

        # 2. Year score
        item_year = it.get('y')
        year_score = 0
        if target_year and item_year:
            year_score = 50 if abs(item_year - target_year) <= 1 else -20
        elif item_year:
            year_score = 10

        # 3. Media Type score
        q_type = it.get('q', '')
        if q_type in ['feature', 'movie']:
            type_score = 60
        elif q_type in ['TV series', 'TV mini-series', 'tvSpecial']:
            type_score = 50
        elif q_type in ['short', 'video', 'podcastEpisode']:
            type_score = -50
        else:
            type_score = 0

        rank = it.get('rank', 999999)
        total_score = title_score + year_score + type_score
        return (-total_score, rank)

    candidates.sort(key=score)
    best = candidates[0]
    title_str = f"{best.get('l')} ({best.get('y')})" if best.get('y') else best.get('l')
    return title_str, f"https://www.imdb.com/title/{best.get('id')}/", best.get('s', '')

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

def is_anime(query, stars=""):
    lower = query.lower()
    if any(k in lower for k in ['anime', 'manga', 'manhwa', 'manhua', 'webtoon', 'donghua', 'light novel', 'crunchyroll']):
        return True
    for f in ANIME_FRANCHISES:
        if f in lower:
            return True
    if stars and re.search(JAPANESE_VOICE_PATTERN, stars, re.IGNORECASE):
        return True
    return False

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
            if is_anime(meta["title"], meta.get("stars", "")):
                result["suggestedCategory"] = "anime"
            else:
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

    # 5. Anime / Manga / Manhwa / TV / Movie Resolution
    if not result["suggestedCategory"]:
        title, imdb_url, stars = lookup_imdb_precise(text)
        if imdb_url:
            result["title"] = title
            result["imdbUrl"] = imdb_url
            if is_anime(text, stars) or is_anime(title, stars):
                result["suggestedCategory"] = "anime"
            else:
                result["suggestedCategory"] = "media"

    return result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query_input = " ".join(sys.argv[1:])
        res = resolve_context(query_input)
        print(json.dumps(res))
    else:
        print(json.dumps({}))
