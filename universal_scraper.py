#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import re
import tempfile
import glob
import urllib.request
import urllib.parse
import http.cookiejar
import html
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
        clean = ''.join(c.lower() for c in query if c.isalnum() or c.isspace()).strip()
        clean = clean.replace(' ', '_')
        if not clean:
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

def search_github_repo(query):
    if not query or len(query.strip()) < 3:
        return ""
    query = query.strip()
    
    # 1. Direct GitHub API search
    try:
        api_url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page=3"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            if items:
                return items[0].get("html_url")
    except Exception:
        pass

    # 2. DuckDuckGo lite search fallback
    try:
        post_data = urllib.parse.urlencode({"q": f"{query} site:github.com"}).encode("utf-8")
        req = urllib.request.Request("https://lite.duckduckgo.com/lite/", data=post_data, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            matches = re.findall(r'(https://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)', content)
            for m in matches:
                if not any(bad in m for bad in ["/features", "/pricing", "/about", "/collections", "/trending", "/topics"]):
                    return m
    except Exception:
        pass

    return ""

def extract_instagram_comments(shortcode, cookies_path, max_comments=100):
    """Extract full paginated comments (up to 100) from Instagram post using GraphQL."""
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
            "Referer": f"https://www.instagram.com/p/{shortcode}/"
        }

        query_hashes = [
            "bc3296d1ce80a24b1b6e40b1e72903f5",
            "b3055c2c9da449f818460d4d3d424125",
            "97b41c52304d77ce08d4debc940da588"
        ]

        for qh in query_hashes:
            all_comments = []
            has_next = True
            cursor = None
            page = 1

            while has_next and len(all_comments) < max_comments and page <= 5:
                vars_dict = {"shortcode": shortcode, "first": 50}
                if cursor:
                    vars_dict["after"] = cursor
                
                encoded_vars = urllib.parse.quote(json.dumps(vars_dict))
                url = f"https://www.instagram.com/graphql/query/?query_hash={qh}&variables={encoded_vars}"
                req = urllib.request.Request(url, headers=headers)
                
                try:
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

    # Check for GitHub and IMDb links
    combined_text = f"{result['title']} {result['caption']} {result['spokenTranscript']}"
    gh_match = re.search(r'https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+', combined_text)
    if gh_match:
        result["githubUrl"] = gh_match.group(0)
    elif result["title"] and any(k in combined_text.lower() for k in ["github", "tool", "project", "open source", "library", "code", "ai"]):
        result["githubUrl"] = search_github_repo(result["title"])

    # Resolve exact IMDb URL
    if result["title"]:
        result["imdbUrl"] = get_exact_imdb_url(result["title"])

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

    # Extract shortcode
    shortcode_match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    shortcode = shortcode_match.group(1) if shortcode_match else ""

    # 1. Metadata
    cmd_json = ["gallery-dl", "-j", "--no-download"]
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
        cmd_json.extend(["--cookies", cookies_path])
    cmd_json.append(url)

    try:
        proc = subprocess.run(cmd_json, capture_output=True, text=True, timeout=30)
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
                        if data.get("likes"):
                            result["likes"] = data.get("likes")
                        if data.get("tags"):
                            result["tags"] = data.get("tags")
    except Exception as e:
        result["error"] = str(e)

    # 2. Extract Full Paginated Comments (up to 100) via GraphQL
    if shortcode:
        comments_text = extract_instagram_comments(shortcode, cookies_path, max_comments=100)
        if comments_text:
            result["comments"] = comments_text

    # 3. Audio & Video frames OCR
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd_dl = ["gallery-dl", "--dest", tmpdir]
        if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
            cmd_dl.extend(["--cookies", cookies_path])
        cmd_dl.append(url)

        try:
            subprocess.run(cmd_dl, capture_output=True, text=True, timeout=60)
            mp4_files = glob.glob(f"{tmpdir}/**/*.mp4", recursive=True)
            if mp4_files:
                video_file = mp4_files[0]
                audio_file = os.path.join(tmpdir, "audio.wav")
                subprocess.run(["ffmpeg", "-y", "-i", video_file, "-vn", "-ar", "16000", "-ac", "1", audio_file], capture_output=True)
                if os.path.exists(audio_file) and os.path.getsize(audio_file) > 1000:
                    try:
                        import speech_recognition as sr
                        r = sr.Recognizer()
                        with sr.AudioFile(audio_file) as source:
                            audio_data = r.record(source)
                        result["spokenTranscript"] = r.recognize_google(audio_data)
                    except Exception:
                        pass

                try:
                    frame_pattern = os.path.join(tmpdir, "frame_%02d.jpg")
                    subprocess.run(["ffmpeg", "-y", "-i", video_file, "-vf", "fps=0.5,scale=1280:-1", frame_pattern], capture_output=True)
                    import pytesseract
                    from PIL import Image
                    frames = sorted(glob.glob(os.path.join(tmpdir, "frame_*.jpg")))
                    ocr_texts = []
                    for f in frames[:6]:
                        text = pytesseract.image_to_string(Image.open(f))
                        clean = " ".join(text.split())
                        if len(clean) > 5 and clean not in ocr_texts:
                            ocr_texts.append(clean)
                    if ocr_texts:
                        result["onScreenText"] = " | ".join(ocr_texts[:3])
                except Exception:
                    pass
        except Exception:
            pass

    # Check for GitHub and IMDb links
    combined_text = f"{result['caption']} {result['comments']} {result['spokenTranscript']} {result['onScreenText']}"
    gh_match = re.search(r'https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+', combined_text)
    if gh_match:
        result["githubUrl"] = gh_match.group(0)
    elif any(k in combined_text.lower() for k in ["github", "repo", "open source", "developer tool", "code repository", "library"]):
        first_line = result["caption"].split("\n")[0] if result["caption"] else ""
        first_clean = re.sub(r'[#@\(\)]', '', first_line).strip()
        if len(first_clean) > 5:
            result["githubUrl"] = search_github_repo(first_clean)

    # Search IMDb for first title
    first_line = result["caption"].split("\n")[0] if result["caption"] else ""
    first_clean = re.sub(r'[#@\(\)]', '', first_line).strip()
    if first_clean and len(first_clean) > 2:
        result["imdbUrl"] = get_exact_imdb_url(first_clean)

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

        # Check for GitHub link
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
