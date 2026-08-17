#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import re
import tempfile
import glob

def scrape_instagram(url):
    cookies_path = "/home/node/.config/gallery-dl/cookies.txt"
    if not os.path.exists(cookies_path):
        cookies_path = "/Users/shariq/discord-n8n/cookies.txt"
    
    result = {
        "caption": "",
        "spokenTranscript": "",
        "onScreenText": "",
        "videoUrl": "",
        "imageUrl": "",
        "author": "",
        "likes": 0,
        "comments": 0,
        "tags": [],
        "rawMetadata": None,
        "error": None
    }
    
    # 1. Run gallery-dl in dump-json mode for fast metadata extraction
    cmd_json = ["gallery-dl", "-j", "--no-download"]
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
        cmd_json.extend(["--cookies", cookies_path])
    cmd_json.append(url)
    
    try:
        proc = subprocess.run(cmd_json, capture_output=True, text=True, timeout=30)
        stdout = proc.stdout
        if stdout.strip():
            raw = json.loads(stdout)
            result["rawMetadata"] = raw
            if isinstance(raw, list):
                for entry in raw:
                    data = entry[1] if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], dict) else (entry if isinstance(entry, dict) else {})
                    if data:
                        if not result["caption"]:
                            result["caption"] = data.get("description") or data.get("caption") or ""
                        if not result["videoUrl"] and (data.get("video_url") or (data.get("url") and ".mp4" in data.get("url", ""))):
                            result["videoUrl"] = data.get("video_url") or data.get("url")
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

    # 2. If it's a video/reel, download the media to transcribe audio and inspect on-screen frames
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
                
                # Extract WAV audio with ffmpeg
                subprocess.run(["ffmpeg", "-y", "-i", video_file, "-vn", "-ar", "16000", "-ac", "1", audio_file], capture_output=True)
                
                # Transcribe spoken audio
                if os.path.exists(audio_file) and os.path.getsize(audio_file) > 1000:
                    try:
                        import speech_recognition as sr
                        r = sr.Recognizer()
                        with sr.AudioFile(audio_file) as source:
                            audio_data = r.record(source)
                        transcript = r.recognize_google(audio_data)
                        result["spokenTranscript"] = transcript
                    except Exception as err:
                        pass
                
                # Extract keyframes and run OCR for on-screen text
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
                except Exception as err:
                    pass
        except Exception as e:
            pass

    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        scrape_instagram(sys.argv[1])
    else:
        print(json.dumps({"error": "No URL provided"}))
