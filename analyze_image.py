#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.parse
import base64
from PIL import Image, ImageEnhance
import pytesseract
import io
import re
import unicodedata

LM_STUDIO_HOST = os.environ.get("LM_STUDIO_HOST", "http://host.docker.internal:1234")

def get_exact_imdb_url(query):
    if not query or len(query.strip()) < 2:
        return ""
    try:
        query = unicodedata.normalize('NFKD', query)
        # Try both direct and normalized query variations
        variations = [
            query,
            query.replace("are", "re").replace("'", ""),
            re.sub(r'[^a-zA-Z0-9\s]', '', query)
        ]
        for var in variations:
            clean = ''.join(c.lower() for c in var if c.isalnum() or c.isspace()).strip().replace(' ', '_')
            if not clean:
                continue
            url = f"https://v3.sg.media-imdb.com/suggestion/x/{urllib.parse.quote(clean)}.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("d", [])
                for item in items:
                    item_id = item.get("id")
                    if item_id and item_id.startswith("tt"):
                        # Prioritize features/series over people
                        q_type = item.get("q", "")
                        if q_type in ["feature", "TV series", "TV mini-series", "movie", "video"]:
                            return f"https://www.imdb.com/title/{item_id}/"
                        return f"https://www.imdb.com/title/{item_id}/"
    except Exception:
        pass
    return ""

def get_active_lm_studio_model():
    try:
        req = urllib.request.Request(f"{LM_STUDIO_HOST}/v1/models", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in data.get("data", [])]
            if not models:
                return None
            vision_models = [m for m in models if any(k in m.lower() for k in ["vl", "vision", "minicpm", "ocr", "gemma", "qwen"])]
            if vision_models:
                return vision_models[0]
            return models[0]
    except Exception:
        return None

def extract_with_vision_ai(image_bytes, timeout=40):
    model_id = get_active_lm_studio_model()
    if not model_id:
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes))
        if max(img.width, img.height) > 1024:
            img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=90)
        b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe and extract all text, ingredients, numbers, titles, and instructions from this image accurately in order. Be 100% faithful to the image text."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_img}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 1200
        }

        req = urllib.request.Request(
            f"{LM_STUDIO_HOST}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content and len(content) > 5:
                return content
    except Exception:
        pass
    return None

def extract_with_enhanced_ocr(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        target_w = max(img.width * 2, 1200)
        target_h = int(img.height * (target_w / img.width))
        img_large = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        gray = img_large.convert("L")
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.2)
        
        texts = []
        for psm in [6, 4, 3, 11]:
            try:
                t = pytesseract.image_to_string(enhanced, config=f"--psm {psm} --oem 3").strip()
                if t:
                    texts.append(t)
            except Exception:
                pass
        
        if texts:
            best = max(texts, key=len)
            lines = [line.strip() for line in best.split("\n") if line.strip()]
            return "\n".join(lines)
    except Exception as e:
        return f"OCR error: {str(e)}"
    return ""

def analyze_image(url_or_path):
    result = {
        "imageText": "",
        "detectedTitle": "",
        "imdbUrl": "",
        "hasText": False,
        "method": "none",
        "error": None
    }

    try:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            req = urllib.request.Request(url_or_path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                image_bytes = resp.read()
        else:
            with open(url_or_path, "rb") as f:
                image_bytes = f.read()

        ai_text = extract_with_vision_ai(image_bytes)
        if ai_text:
            result["imageText"] = ai_text
            result["hasText"] = True
            result["method"] = "ai_vision"
        else:
            ocr_text = extract_with_enhanced_ocr(image_bytes)
            result["imageText"] = ocr_text
            result["hasText"] = len(ocr_text) > 5
            result["method"] = "enhanced_ocr"

        # Discover movie/show title and IMDb link from extracted image text
        if result["imageText"]:
            lines = [l.strip() for l in result["imageText"].splitlines() if l.strip()]
            for l in lines[:5]:
                clean_l = re.sub(r'[#@\(\)0-9:·•]', ' ', l).strip()
                if len(clean_l) >= 3 and clean_l.lower() not in ["google", "search", "trailer", "youtube", "cbfc", "where to watch"]:
                    imdb = get_exact_imdb_url(clean_l)
                    if imdb:
                        result["detectedTitle"] = clean_l
                        result["imdbUrl"] = imdb
                        break

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_image(sys.argv[1])
    else:
        print(json.dumps({"error": "No URL provided"}))
