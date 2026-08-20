#!/bin/bash
# Script to configure macOS Login Items for media stack & startup scripts

echo "Configuring macOS Login Items..."

osascript << 'APPLESCRIPT'
tell application "System Events"
    set appList to { ¬
        {appPath:"/Applications/Sonarr.app", appName:"Sonarr"}, ¬
        {appPath:"/Applications/Radarr.app", appName:"Radarr"}, ¬
        {appPath:"/Applications/Prowlarr.app", appName:"Prowlarr"}, ¬
        {appPath:"/Users/shariq/Desktop/start-n8n-ngrok.command alias", appName:"start-n8n-ngrok.command alias"}, ¬
        {appPath:"/Users/shariq/Desktop/start.command alias", appName:"start.command alias"} ¬
    }
    
    set existingItems to name of every login item
    repeat with anItem in appList
        set p to appPath of anItem
        set n to appName of anItem
        if n is not in existingItems then
            try
                make login item at end with properties {path:p, hidden:false}
                log "Added " & n & " to Login Items."
            on error errMsg
                log "Failed to add " & n & ": " & errMsg
            end try
        else
            log n & " is already in Login Items."
        end if
    end repeat
end tell
APPLESCRIPT

echo "Current Login Items:"
osascript -e 'tell application "System Events" to get name of every login item'
