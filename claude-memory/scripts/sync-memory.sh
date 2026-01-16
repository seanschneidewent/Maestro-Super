#!/bin/bash

# Load environment
source "$(dirname "$0")/../.env"

API="$SUPABASE_URL/rest/v1"
AUTH="-H \"apikey: $SUPABASE_KEY\" -H \"Authorization: Bearer $SUPABASE_KEY\""

OUTPUT="$(dirname "$0")/../CONTEXT.md"

echo "# Claude Memory Context" > "$OUTPUT"
echo "Generated: $(date)" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Covenant
echo "## Covenant" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/covenant?select=content&limit=1" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[0].content' >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Identity
echo "## Identity" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/identity?select=key,value" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[] | "**\(.key):** \(.value)"' >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Operating Principles
echo "## Operating Principles" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/operating_principles?select=principle,example" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[] | "- **\(.principle):** \(.example)"' >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Current Edge
echo "## Current Edge" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/current_edge?select=*&order=updated_at.desc&limit=1" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[] | "**Project:** \(.project)\n**What shipping looks like:** \(.what_shipping_looks_like)\n**Next step:** \(.specific_next_step)\n**Exposure:** \(.what_feels_like_exposure)"' >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Projects
echo "## Projects" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/projects?select=name,status,next_action,blockers" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[] | "### \(.name)\n- Status: \(.status)\n- Next: \(.next_action)\n- Blockers: \(.blockers)\n"' >> "$OUTPUT"

# Recent Decisions
echo "## Recent Decisions" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/decisions?select=date,domain,decision,rationale&order=date.desc&limit=5" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[] | "**[\(.date)] \(.domain):** \(.decision)\n- *Rationale:* \(.rationale)\n"' >> "$OUTPUT"

# Relationships
echo "## Key Relationships" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/relationships?select=name,role,context,network" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[] | "- **\(.name)** (\(.role), \(.network)): \(.context)"' >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Recent Sessions
echo "## Recent Sessions" >> "$OUTPUT"
echo "" >> "$OUTPUT"
curl -s "$API/conversations?select=session_date,interface,project,summary,next_session_hint&order=created_at.desc&limit=5" \
  -H "apikey: $SUPABASE_KEY" | jq -r '.[] | "### [\(.session_date)] \(.interface) — \(.project)\n\(.summary)\n**Next:** \(.next_session_hint)\n"' >> "$OUTPUT"

echo "Memory synced to $OUTPUT"
