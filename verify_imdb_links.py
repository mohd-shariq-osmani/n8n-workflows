#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.parse
import re
import unicodedata

def lookup_imdb_precise(title_query):
    if not title_query or len(title_query.strip()) < 2:
        return None, ""
        
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

def verify_and_patch_markdown(markdown_text):
    if not markdown_text:
        return markdown_text

    # 1. Extract H1 Header Title (e.g. # 🎬 Argylle (2024) or # 🎌 The Brilliant Healer...)
    h1_match = re.search(r'^#\s+(?:🎬|🎌|🎥|📺|🎞️|🍿)?\s*[\*\_]*([^\n\*\_]+)[\*\_]*', markdown_text, re.MULTILINE)
    h1_title = h1_match.group(1).strip() if h1_match else ""

    # 2. Extract Recommended Titles list if present
    # e.g. • **Black Sails (2014–2016)**: ...
    bullet_titles = re.findall(r'•\s+\*\*([^\*:]+)\*\*', markdown_text)

    # 3. Lookup verified IMDb link for primary title
    primary_link = ""
    if h1_title:
        _, primary_link = lookup_imdb_precise(h1_title)
    
    if not primary_link and bullet_titles:
        _, primary_link = lookup_imdb_precise(bullet_titles[0])

    # 4. If we found a verified IMDb link, replace or append in Markdown
    if primary_link:
        if re.search(r'🎬?\s*\*\*IMDb:\*\*\s*\S+', markdown_text):
            markdown_text = re.sub(r'🎬?\s*\*\*IMDb:\*\*\s*\S+', f'🎬 **IMDb:** {primary_link}', markdown_text)
        elif re.search(r'https?://(?:www\.)?imdb\.com/title/tt\d+/?', markdown_text):
            markdown_text = re.sub(r'https?://(?:www\.)?imdb\.com/title/tt\d+/?', primary_link, markdown_text)
        else:
            # Append before Where to Watch or at the end
            if "📺 **Where to Watch:**" in markdown_text:
                markdown_text = markdown_text.replace("📺 **Where to Watch:**", f"🎬 **IMDb:** {primary_link}\n📺 **Where to Watch:**")
            elif "🔗 **Source:**" in markdown_text:
                markdown_text = markdown_text.replace("🔗 **Source:**", f"🎬 **IMDb:** {primary_link}\n🔗 **Source:**")
            else:
                markdown_text += f"\n\n🎬 **IMDb:** {primary_link}"

    return markdown_text

if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_text = sys.argv[1]
        print(verify_and_patch_markdown(input_text))
    else:
        raw_in = sys.stdin.read()
        print(verify_and_patch_markdown(raw_in))
