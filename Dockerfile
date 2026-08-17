FROM python:3.12-alpine AS builder

RUN apk add --no-cache ffmpeg flac tesseract-ocr tesseract-ocr-data-eng
RUN pip install --no-cache-dir gallery-dl yt-dlp SpeechRecognition pytesseract Pillow beautifulsoup4

FROM docker.n8n.io/n8nio/n8n:latest

USER root

# Copy python3, pip, tools and packages from alpine builder
COPY --from=builder /usr/local /usr/local
COPY --from=builder /usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=builder /usr/bin/ffprobe /usr/bin/ffprobe
COPY --from=builder /usr/bin/flac /usr/bin/flac
COPY --from=builder /usr/bin/tesseract /usr/bin/tesseract
COPY --from=builder /usr/share/tessdata /usr/share/tessdata
COPY --from=builder /usr/lib /usr/lib

ENV TESSDATA_PREFIX=/usr/share/tessdata

COPY universal_scraper.py /usr/local/bin/universal_scraper.py
COPY scrape_instagram.py /usr/local/bin/scrape_instagram.py
COPY analyze_image.py /usr/local/bin/analyze_image.py
RUN chmod +x /usr/local/bin/universal_scraper.py /usr/local/bin/scrape_instagram.py /usr/local/bin/analyze_image.py

USER node
