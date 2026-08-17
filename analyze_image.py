#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.error
import base64
import tempfile
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import io

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://192.168.0.50:1234/v1/chat/completions")

def extract_with_vision_ai(image_bytes, timeout=12):
    """Attempt to extract text using Vision LLM in LM Studio."""
    try:
        # Resize image for fast vision tokenization
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((768, 768))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

        payload = {
            "model": "default",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcribe and extract all text, ingredients, numbers, and instructions from this image accurately in order. Output only the extracted content."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }

        req = urllib.request.Request(
            LM_STUDIO_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content and len(content) > 10:
                return content
    except Exception:
        pass
    return None

def extract_with_enhanced_ocr(image_bytes):
    """High-contrast preprocessed Tesseract OCR fallback."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # 1. Upscale for small/handwritten fonts
        target_w = max(img.width * 2, 1200)
        target_h = int(img.height * (target_w / img.width))
        img_large = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # 2. Convert to Grayscale & enhance contrast
        gray = img_large.convert("L")
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.2)
        
        # 3. Multi-PSM scanning (PSM 6: Uniform block of text, PSM 4: Column text, PSM 3: Default page)
        texts = []
        for psm in [6, 4, 3]:
            try:
                t = pytesseract.image_to_string(enhanced, config=f"--psm {psm} --oem 3").strip()
                if t:
                    texts.append(t)
            except Exception:
                pass
        
        if texts:
            # Pick the longest/most complete transcription
            best = max(texts, key=len)
            # Clean empty lines
            lines = [line.strip() for line in best.split("\n") if line.strip()]
            return "\n".join(lines)
    except Exception as e:
        return f"OCR error: {str(e)}"
    return ""

def analyze_image(url_or_path):
    result = {
        "imageText": "",
        "hasText": False,
        "method": "none",
        "error": None
    }

    try:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            req = urllib.request.Request(url_or_path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                image_bytes = resp.read()
        else:
            with open(url_or_path, "rb") as f:
                image_bytes = f.read()

        # Step 1: Try AI Vision Agent (LM Studio)
        ai_text = extract_with_vision_ai(image_bytes)
        if ai_text:
            result["imageText"] = ai_text
            result["hasText"] = True
            result["method"] = "ai_vision"
        else:
            # Step 2: Fallback to Enhanced Preprocessed OCR
            ocr_text = extract_with_enhanced_ocr(image_bytes)
            result["imageText"] = ocr_text
            result["hasText"] = len(ocr_text) > 5
            result["method"] = "enhanced_ocr"

    except Exception as e:
        result["error"] = str(e)

    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_image(sys.argv[1])
    else:
        print(json.dumps({"error": "No URL provided"}))
