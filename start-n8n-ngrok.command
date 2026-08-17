#!/bin/bash

# Path to your project folder — edit this if you move the folder
PROJECT_DIR="$HOME/discord-n8n"

# Your fixed n8n URL — this no longer changes between restarts
N8N_URL="https://customize-crouton-mobility.ngrok-free.dev"

echo "Starting Docker Desktop (if not already running)..."
open -a Docker

# Wait for Docker to actually be ready before running compose
echo "Waiting for Docker to be ready..."
until docker system info > /dev/null 2>&1; do
  sleep 2
done
echo "Docker is ready."

cd "$PROJECT_DIR" || {
  echo "Could not find project folder at $PROJECT_DIR"
  echo "Edit PROJECT_DIR at the top of this script to match your actual folder path."
  read -p "Press Enter to close..."
  exit 1
}

echo "Starting n8n, Discord bot, and ngrok tunnel..."
docker compose up -d

echo "Waiting for everything to come online..."
sleep 8

echo ""
echo "Your n8n URL (always the same):"
echo "$N8N_URL"

echo ""
echo "Opening in your browser..."
open "$N8N_URL"

echo ""
echo "All set. You can close this window."
read -p "Press Enter to close..."
