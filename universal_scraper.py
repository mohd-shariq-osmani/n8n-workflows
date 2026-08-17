#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import re
import tempfile
import glob
import time
import random
import urllib.request
import urllib.parse
import http.cookiejar
import html
import unicodedata
from bs4 import BeautifulSoup

def clean_vtt(vtt_text):
    lines = []
    for line in vtt_text.splitlines():
        line = line.strip()
        if not line or '-->' in line or line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:') or line.startswith('Style:') or line.startswith('NOTE'):
            continue
        clean = re.sub(r'<[^>]+>', '', line).strip()
        if clean and (not lines or clean != lines[-1]):
            lines.append(clean)
    return ' '.join(lines)

def transcribe_audio_file(audio_path):
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
        return ""
    try:
        import speech_recognition as sr
        wav_path = audio_path.rsplit('.', 1)[0] + '.wav'
        subprocess.run(['ffmpeg', '-y', '-i', audio_path, '-vn', '-ar', '16000', '-ac', '1', wav_path], capture_output=True)
        if os.path.exists(wav_path):
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
            text = r.recognize_google(audio_data)
            if os.path.exists(wav_path):
                os.remove(wav_path)
            return text
    except Exception:
        pass
    return ""

def get_exact_imdb_url(query):
    if not query or len(query.strip()) < 2:
        return ""
    try:
        query = unicodedata.normalize('NFKD', query)
        clean = ''.join(c.lower() for c in query if c.isalnum() or c.isspace()).strip()
        clean = clean.replace(' ', '_')
        if not clean or clean in ["movie", "movie_name", "film", "series", "anime", "name", "anime_name"]:
            return ""
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{urllib.parse.quote(clean)}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("d", [])
            for item in items:
                item_id = item.get("id")
                if item_id and item_id.startswith("tt"):
                    return f"https://www.imdb.com/title/{item_id}/"
    except Exception:
        pass
    return ""

def clean_project_query(text):
    if not text:
        return ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    filtered = []
    for l in lines:
        if re.search(r'(comment\s+[\"“\']|dm\s+me|link\s+in\s+bio|save\s+this|follow\s+for|double\s+tap|send\s+you|download\s+link)', l, re.IGNORECASE):
            continue
        filtered.append(l)

    cleaned = " ".join(filtered)
    m = re.search(r'([A-Za-z0-9\-_]{2,25})\s+is\s+an?\s+(?:open[\-\s]source|ai|tool|framework|library|workstation|app|orchestrator|ide|system)', cleaned, re.IGNORECASE)
    if m:
        return f"{m.group(1)} open source"

    first_chunk = filtered[0] if filtered else text.split("\n")[0]
    first_chunk = re.sub(r'[#@\(\)🟢🔥🚀✨💡]', '', first_chunk).strip()
    return first_chunk[:60]

def search_github_repo(query):
    if not query or len(query.strip()) < 2:
        return ""
    
    clean_q = clean_project_query(query)
    if not clean_q:
        clean_q = query.strip()

    try:
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": f"{clean_q} github"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": "https://html.duckduckgo.com/"
            }
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
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

def extract_instagram_comments(shortcode, cookies_path, max_comments=75):
    """Extract comments safely with rate-limiting, jitter, and browser fingerprinting."""
    if not os.path.exists(cookies_path) or not shortcode:
        return ""
    
    try:
        cj = http.cookiejar.MozillaCookieJar(cookies_path)
        cj.load()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

        csrf = ""
        for c in cj:
            if c.name == "csrftoken":
                csrf = c.value

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "129477",
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.instagram.com/p/{shortcode}/",
            "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Accept-Language": "en-US,en;q=0.9"
        }

        query_hash = "bc3296d1ce80a24b1b6e40b1e72903f5"
        all_comments = []
        has_next = True
        cursor = None
        page = 1

        while has_next and len(all_comments) < max_comments and page <= 3:
            vars_dict = {"shortcode": shortcode, "first": 40}
            if cursor:
                vars_dict["after"] = cursor
            
            encoded_vars = urllib.parse.quote(json.dumps(vars_dict))
            url = f"https://www.instagram.com/graphql/query/?query_hash={query_hash}&variables={encoded_vars}"
            req = urllib.request.Request(url, headers=headers)
            
            try:
                if page > 1:
                    time.sleep(random.uniform(1.2, 2.2))

                with opener.open(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    comment_data = data.get("data", {}).get("shortcode_media", {}).get("edge_media_to_parent_comment", {})
                    edges = comment_data.get("edges", [])
                    page_info = comment_data.get("page_info", {})
                    
                    if not edges:
                        break

                    for e in edges:
                        node = e.get("node", {})
                        u = node.get("owner", {}).get("username", "user")
                        t = node.get("text", "").strip()
                        if t and not any(t in existing for existing in all_comments):
                            if node.get("is_pinned") or node.get("is_pinned_by_creator"):
                                all_comments.append(f"[PINNED by @{u}]: {t}")
                            else:
                                all_comments.append(f"@{u}: {t}")
                    
                    has_next = page_info.get("has_next_page", False)
                    cursor = page_info.get("end_cursor")
                    page += 1
            except Exception:
                break

        if all_comments:
            return "\n".join(all_comments)

    except Exception:
        pass
    return ""

def find_imdb_in_text(caption_text, comments_text=""):
    if caption_text:
        norm_cap = unicodedata.normalize('NFKD', caption_text)
        cap_patterns = [
            r'(?:title|name)[:\s\-]+([A-Za-z0-9\'\s]{3,60})',
            r'(?:anime|donghua|manga|manhwa|movie|series)[:\s\-]+([A-Za-z0-9\'\s]{3,60})',
        ]
        for p in cap_patterns:
            matches = re.findall(p, norm_cap, re.IGNORECASE)
            for m in matches:
                clean = m.strip().split("\n")[0].split(".")[0].strip()
                if len(clean) >= 3 and clean.lower() not in ["info", "name", "title", "ongoing", "yes", "season"]:
                    url = get_exact_imdb_url(clean)
                    if url:
                        return url

    if comments_text:
        comm_patterns = [
            r'(?:movie(?:\s+name)?[:\s\-]+)([A-Za-z0-9\'\s]{3,40})',
            r'(?:anime(?:\s+name)?[:\s\-]+)([A-Za-z0-9\'\s]{3,40})',
            r'(?:series(?:\s+name)?[:\s\-]+)([A-Za-z0-9\'\s]{3,40})',
            r'(?:film(?:\s+name)?[:\s\-]+)([A-Za-z0-9\'\s]{3,40})',
        ]
        for p in comm_patterns:
            matches = re.findall(p, comments_text, re.IGNORECASE)
            for m in matches:
                clean = m.strip().split("\n")[0].split(".")[0].strip()
                if len(clean) >= 3 and clean.lower() not in ["name", "pls", "please", "bro", "redo of healer"]:
                    url = get_exact_imdb_url(clean)
                    if url:
                        return url

    return ""

def scrape_youtube(url):
    result = {
        "title": "",
        "caption": "",
        "spokenTranscript": "",
        "onScreenText": "",
        "comments": "",
        "githubUrl": "",
        "imdbUrl": "",
        "videoUrl": url,
        "imageUrl": "",
        "author": "",
        "likes": 0,
        "tags": [],
        "sourceType": "youtube",
        "error": None
    }
    
    try:
        cmd = ['yt-dlp', '--dump-single-json', '--skip-download', '--no-warnings', url]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.stdout.strip():
            meta = json.loads(proc.stdout)
            result["title"] = meta.get("title", "")
            result["caption"] = meta.get("description", "")
            result["author"] = meta.get("uploader", "") or meta.get("channel", "")
            result["imageUrl"] = meta.get("thumbnail", "")
            result["likes"] = meta.get("like_count", 0)
            result["tags"] = meta.get("tags", [])
            
            subs = meta.get("subtitles", {}) or {}
            auto_subs = meta.get("automatic_captions", {}) or {}
            
            target_sub = None
            for key in ["en", "en-US", "en-GB", "en-orig", "a.en", "hi", "auto"]:
                if key in subs:
                    target_sub = subs[key]
                    break
                if key in auto_subs:
                    target_sub = auto_subs[key]
                    break
                    
            if not target_sub:
                for k, v in {**subs, **auto_subs}.items():
                    if k.startswith("en"):
                        target_sub = v
                        break
                        
            if not target_sub and (subs or auto_subs):
                target_sub = list({**subs, **auto_subs}.values())[0]

            if target_sub:
                sub_url = None
                for fmt in target_sub:
                    if fmt.get("ext") == "json3":
                        sub_url = fmt.get("url")
                        break
                if not sub_url:
                    for fmt in target_sub:
                        if fmt.get("ext") in ["vtt", "srv3"]:
                            sub_url = fmt.get("url")
                            break
                if not sub_url and target_sub:
                    sub_url = target_sub[0].get("url")

                if sub_url:
                    try:
                        req = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            sub_raw = resp.read().decode("utf-8", errors="ignore")
                        
                        if sub_raw.strip().startswith("{"):
                            data = json.loads(sub_raw)
                            parts = []
                            for ev in data.get("events", []):
                                for seg in ev.get("segs", []):
                                    u = seg.get("utf8", "")
                                    if u and u != "\n":
                                        parts.append(u.strip())
                            transcript = " ".join(parts)
                        else:
                            transcript = clean_vtt(sub_raw)
                            
                        if len(transcript) > 20:
                            result["spokenTranscript"] = transcript[:5000]
                    except Exception:
                        pass
    except Exception as e:
        result["error"] = f"YouTube scrape error: {str(e)}"

    if not result["spokenTranscript"]:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                audio_file = os.path.join(tmpdir, "yt_audio.mp3")
                cmd_audio = [
                    "yt-dlp",
                    "-f", "ba[ext=m4a]/ba/b",
                    "--max-filesize", "15M",
                    "-x",
                    "--audio-format", "mp3",
                    "--no-warnings",
                    "-o", audio_file,
                    url
                ]
                subprocess.run(cmd_audio, capture_output=True, text=True, timeout=45)
                if os.path.exists(audio_file):
                    result["spokenTranscript"] = transcribe_audio_file(audio_file)
            except Exception:
                pass

    combined_text = f"{result['title']} {result['caption']} {result['spokenTranscript']}"
    gh_match = re.search(r'https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+', combined_text)
    if gh_match:
        result["githubUrl"] = gh_match.group(0)
    elif result["title"] and any(k in combined_text.lower() for k in ["github", "tool", "project", "open source", "library", "code", "ai"]):
        result["githubUrl"] = search_github_repo(result["title"])

    if result["title"]:
        result["imdbUrl"] = get_exact_imdb_url(result["title"])
    if not result["imdbUrl"]:
        result["imdbUrl"] = find_imdb_in_text(result["caption"], result["comments"])

    return result

def scrape_instagram(url):
    cookies_path = "/home/node/.config/gallery-dl/cookies.txt"
    if not os.path.exists(cookies_path):
        cookies_path = "/Users/shariq/discord-n8n/cookies.txt"

    result = {
        "title": "",
        "caption": "",
        "spokenTranscript": "",
        "onScreenText": "",
        "comments": "",
        "githubUrl": "",
        "imdbUrl": "",
        "videoUrl": url,
        "imageUrl": "",
        "author": "",
        "likes": 0,
        "tags": [],
        "sourceType": "instagram",
        "error": None
    }

    shortcode_match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    shortcode = shortcode_match.group(1) if shortcode_match else ""

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Fetch Metadata with yt-dlp (fast & unauthenticated)
        try:
            cmd_meta = ["yt-dlp", "--dump-single-json", "--skip-download", "--no-warnings", url]
            proc_meta = subprocess.run(cmd_meta, capture_output=True, text=True, timeout=20)
            if proc_meta.stdout.strip():
                meta_y = json.loads(proc_meta.stdout)
                result["caption"] = meta_y.get("description") or meta_y.get("title") or ""
                result["author"] = meta_y.get("uploader") or meta_y.get("channel") or ""
                result["imageUrl"] = meta_y.get("thumbnail") or ""
                result["likes"] = meta_y.get("like_count", 0)
                result["tags"] = meta_y.get("tags", [])
        except Exception:
            pass

        # 2. Download Video Stream directly with yt-dlp
        video_out = os.path.join(tmpdir, "video.mp4")
        try:
            cmd_dl = ["yt-dlp", "--no-warnings", "-o", video_out, url]
            subprocess.run(cmd_dl, capture_output=True, text=True, timeout=45)
        except Exception:
            pass

        # 3. Transcribe Spoken Video Audio with SpeechRecognition
        if os.path.exists(video_out) and os.path.getsize(video_out) > 1000:
            try:
                audio_file = os.path.join(tmpdir, "audio.wav")
                subprocess.run(["ffmpeg", "-y", "-i", video_out, "-vn", "-ar", "16000", "-ac", "1", audio_file], capture_output=True)
                if os.path.exists(audio_file):
                    result["spokenTranscript"] = transcribe_audio_file(audio_file)
            except Exception:
                pass

            # 4. Extract On-Screen Keyframes with Tesseract OCR
            try:
                frame_pattern = os.path.join(tmpdir, "frame_%02d.jpg")
                subprocess.run(["ffmpeg", "-y", "-i", video_out, "-vf", "fps=0.5,scale=1280:-1", frame_pattern], capture_output=True)
                import pytesseract
                from PIL import Image
                frames = sorted(glob.glob(os.path.join(tmpdir, "frame_*.jpg")))
                ocr_texts = []
                for f in frames[:8]:
                    t = pytesseract.image_to_string(Image.open(f))
                    clean = " ".join(t.split())
                    if len(clean) > 4 and clean not in ocr_texts:
                        ocr_texts.append(clean)
                if ocr_texts:
                    result["onScreenText"] = " | ".join(ocr_texts[:4])
            except Exception:
                pass

    # 5. Fallback metadata via gallery-dl if caption still empty
    if not result["caption"]:
        cmd_json = ["gallery-dl", "-j", "--no-download"]
        if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
            cmd_json.extend(["--cookies", cookies_path])
        cmd_json.append(url)

        try:
            proc = subprocess.run(cmd_json, capture_output=True, text=True, timeout=20)
            stdout = proc.stdout
            if stdout.strip():
                raw = json.loads(stdout)
                if isinstance(raw, list):
                    for entry in raw:
                        data = entry[1] if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], dict) else (entry if isinstance(entry, dict) else {})
                        if data:
                            if not result["caption"]:
                                result["caption"] = data.get("description") or data.get("caption") or ""
                            if not result["imageUrl"]:
                                result["imageUrl"] = data.get("display_url") or data.get("thumbnail") or ""
                            if not result["author"]:
                                result["author"] = data.get("username") or data.get("author") or ""
        except Exception:
            pass

    # 6. Extract Comments safely
    if shortcode:
        comments_text = extract_instagram_comments(shortcode, cookies_path, max_comments=75)
        if comments_text:
            result["comments"] = comments_text

    # 7. Check for GitHub and IMDb links
    combined_text = f"{result['caption']} {result['comments']} {result['spokenTranscript']} {result['onScreenText']}"
    gh_match = re.search(r'https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+', combined_text)
    if gh_match:
        result["githubUrl"] = gh_match.group(0)
    elif any(k in combined_text.lower() for k in ["github", "repo", "open source", "developer tool", "code repository", "library", "workstation", "orchestrator", "ai tool"]):
        search_target = result["caption"] or result["onScreenText"] or result["title"]
        result["githubUrl"] = search_github_repo(search_target)

    result["imdbUrl"] = find_imdb_in_text(result["caption"], result["comments"])

    return result

def scrape_webpage(url):
    result = {
        "title": "",
        "caption": "",
        "spokenTranscript": "",
        "onScreenText": "",
        "comments": "",
        "githubUrl": "",
        "imdbUrl": "",
        "videoUrl": url,
        "imageUrl": "",
        "author": "",
        "likes": 0,
        "tags": [],
        "sourceType": "webpage",
        "error": None
    }
    
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_html = resp.read(250000).decode("utf-8", errors="ignore")
            
        soup = BeautifulSoup(raw_html, "html.parser")
        
        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()
        elif soup.find("meta", property="og:title"):
            result["title"] = soup.find("meta", property="og:title").get("content", "").strip()

        meta_desc = (
            soup.find("meta", attrs={"name": "description"}) or
            soup.find("meta", property="og:description") or
            soup.find("meta", attrs={"name": "twitter:description"})
        )
        if meta_desc and meta_desc.get("content"):
            result["caption"] = meta_desc["content"].strip()

        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            result["imageUrl"] = og_img["content"].strip()

        site_name = soup.find("meta", property="og:site_name")
        if site_name and site_name.get("content"):
            result["author"] = site_name["content"].strip()

        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.decompose()
            
        paragraphs = []
        for p in soup.find_all(["p", "article", "section", "h1", "h2", "h3", "li"]):
            txt = p.get_text(strip=True)
            if len(txt) > 25 and txt not in paragraphs:
                paragraphs.append(txt)
                
        main_text = "\n".join(paragraphs[:15])
        if main_text:
            result["onScreenText"] = main_text[:2500]

        if "github.com" in url:
            result["githubUrl"] = url
        else:
            gh_match = re.search(r'https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+', raw_html)
            if gh_match:
                result["githubUrl"] = gh_match.group(0)
            elif result["title"] and any(k in raw_html.lower() for k in ["github", "repository", "open-source", "npm", "pip"]):
                result["githubUrl"] = search_github_repo(result["title"])

        if result["title"]:
            result["imdbUrl"] = get_exact_imdb_url(result["title"])
        if not result["imdbUrl"]:
            result["imdbUrl"] = find_imdb_in_text(raw_html)
            
    except Exception as e:
        result["error"] = str(e)
        
    return result

def universal_scrape(url):
    clean_url = url.strip().strip("<>\"'")
    lower = clean_url.lower()
    
    if "youtube.com" in lower or "youtu.be" in lower:
        data = scrape_youtube(clean_url)
    elif "instagram.com" in lower:
        data = scrape_instagram(clean_url)
    elif any(d in lower for d in ["tiktok.com", "twitter.com", "x.com", "reddit.com"]):
        try:
            data = scrape_youtube(clean_url)
            data["sourceType"] = "social_video"
        except Exception:
            data = scrape_webpage(clean_url)
    else:
        data = scrape_webpage(clean_url)
        
    print(json.dumps(data))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        universal_scrape(sys.argv[1])
    else:
        print(json.dumps({"error": "No URL provided"}))
