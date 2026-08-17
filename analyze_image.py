#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import tempfile
from PIL import Image
import pytesseract

def analyze_image(url_or_path):
    result = {
        "imageText": "",
        "hasText": False,
        "error": None
    }
    
    try:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            req = urllib.request.Request(url_or_path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(data)
                temp_path = f.name
            img = Image.open(temp_path)
        else:
            img = Image.open(url_or_path)
            temp_path = None
        
        text = pytesseract.image_to_string(img)
        clean = " ".join(text.split())
        result["imageText"] = clean
        result["hasText"] = len(clean) > 5
        
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception as e:
        result["error"] = str(e)
        
    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_image(sys.argv[1])
    else:
        print(json.dumps({"error": "No URL provided"}))
