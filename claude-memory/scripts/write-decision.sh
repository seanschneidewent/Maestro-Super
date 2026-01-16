#!/bin/bash

source "$(dirname "$0")/../.env"

if [ "$#" -lt 2 ]; then
    echo "Usage: ./write-decision.sh <domain> <decision> [rationale]"
    echo "Domains: technical, strategic, product, personal"
    exit 1
fi

DOMAIN="$1"
DECISION="$2"
RATIONALE="${3:-No rationale provided}"
DATE=$(date +%Y-%m-%d)

curl -s -X POST "$SUPABASE_URL/rest/v1/decisions" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Authorization: Bearer $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -H "Prefer: return=minimal" \
  -d "{\"date\": \"$DATE\", \"domain\": \"$DOMAIN\", \"decision\": \"$DECISION\", \"rationale\": \"$RATIONALE\"}"

echo "Decision logged: [$DOMAIN] $DECISION"
