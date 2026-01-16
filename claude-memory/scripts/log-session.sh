#!/bin/bash

source "$(dirname "$0")/../.env"

# Takes JSON as argument - Claude can call this directly
JSON_DATA="$1"

if [ -z "$JSON_DATA" ]; then
    echo "Usage: ./log-session.sh '<json>'"
    echo ""
    echo "Example:"
    echo './log-session.sh '\''{"interface":"claude_code","project":"Maestro","summary":"Fixed auth bug","what_got_built":"JWT refresh logic","problems_solved":"Token expiration","key_decisions":"Use refresh tokens","open_threads":"None","next_session_hint":"Start on OCR"}'\'''
    exit 1
fi

curl -s -X POST "$SUPABASE_URL/rest/v1/conversations" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Authorization: Bearer $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -H "Prefer: return=minimal" \
  -d "$JSON_DATA"

echo "Session logged."
