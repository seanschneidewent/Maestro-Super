# AI Prompt Templates

Reference prompts for the three-pass processing pipeline and query system.

**Models used:**
- **Gemini** - Context extraction (Pass 1, 2, 3) and pointer analysis
- **Claude** - Query responses and walkthroughs

---

## Pass 1: Page Analysis Prompt

```
You are analyzing a construction plan page. Given the page metadata and highlighted regions (context pointers) with their extracted text, provide structured analysis.

Page: {sheet_number} - {page_title}
Pointers: {pointers_with_text_content}

Return JSON:
{
  "discipline": "A|S|M|E|P|FP|C|L|G",
  "sheet_number": "extracted from title block",
  "summary": "2-3 sentences describing what a superintendent would find here",
  "pointers": [
    {
      "pointer_id": "...",
      "summary": "one sentence describing this region",
      "outbound_refs": [
        {
          "ref": "target sheet number",
          "type": "detail|sheet|section|elevation|schedule",
          "source_element_id": "text element ID if available",
          "source_text": "exact text containing the reference"
        }
      ]
    }
  ]
}

Guidelines:
- Identify discipline from CONTENT, not sheet number prefix
- Extract actual sheet number from title block area
- Focus summaries on information useful to superintendents
- Capture ALL cross-references to other sheets
```

---

## Pass 2: Cross-Reference Context Prompt

```
You have a page with outbound references to other sheets. Given summaries of all other pages in the project, provide context for each reference.

This Page: {sheet_number}
Outbound References: {outbound_refs}
Other Page Summaries: {all_page_summaries}

Return JSON:
{
  "outbound_refs_context": [
    {
      "ref": "E-3.2",
      "context": "1-2 sentences explaining what information the superintendent will find when following this reference"
    }
  ]
}

Guidelines:
- Match refs to page summaries by normalized sheet number
- Explain the relationship, not just repeat the summary
- Focus on why a superintendent would follow this reference
```

---

## Pass 3: Discipline Rollup Prompt

```
You are summarizing an entire discipline (trade) across all its sheets. Given all page contexts for this discipline, create a comprehensive summary.

Discipline: {discipline_code} - {discipline_name}
Pages: {pages_with_context}

Return JSON:
{
  "context": "Dense paragraph (3-5 sentences) describing what information lives in this discipline",
  "key_contents": [
    {
      "item": "name of important item",
      "type": "schedule|spec|diagram|detail|plan",
      "sheet": "sheet number where found"
    }
  ],
  "connections": [
    {
      "discipline": "other discipline code",
      "relationship": "how this discipline connects to the other"
    }
  ]
}

Guidelines:
- Be comprehensive but concise
- Prioritize items a superintendent would search for
- Identify cross-discipline dependencies
- key_contents should be searchable terms
```

---

## Context Pointer Analysis Prompt (Single Pointer)

```
Analyze this highlighted region from a construction plan.

Image: {base64_image}
Page: {page_number} of {source_file}
Existing Title: {title}
Existing Description: {description}
Extracted Text: {text_content}

Return JSON:
{
  "technicalDescription": "detailed technical description",
  "tradeCategory": "ELEC|MECH|PLMB|HVAC|FIRE|STRUCT|ARCH|CIVIL|GEN",
  "identifiedElements": [
    {"name": "element name", "type": "element type", "details": "specifics"}
  ],
  "measurements": [
    {"value": "12", "unit": "inches", "context": "conduit diameter"}
  ],
  "issues": [
    {"severity": "warning|info", "description": "potential issue"}
  ],
  "recommendations": "any recommendations for the superintendent"
}
```

---

## Query → Context Retrieval Prompt

Used to find relevant context pointers for a user query.

```
A superintendent is asking about their construction project. Find the most relevant context pointers to answer their question.

Question: {query_text}

Available Context:
- Discipline Summaries: {discipline_contexts}
- Page Summaries: {page_contexts}
- Pointer Summaries: {pointer_summaries}

Return JSON:
{
  "relevant_pointers": [
    {
      "pointer_id": "...",
      "relevance_score": 0.95,
      "reason": "why this pointer is relevant"
    }
  ],
  "relevant_pages": ["E-2.1", "E-3.2"],
  "search_strategy": "brief explanation of how you found these"
}

Return max 10 pointers, ordered by relevance.
```

---

## Query Response Prompt (Claude)

```
You are helping a construction superintendent understand their project plans.

User Question: {query_text}

Relevant Context:
{formatted_context_pointers}

{formatted_page_contexts}

Instructions:
1. Answer the question directly and specifically
2. Reference exact sheet numbers when citing information
3. If showing a walkthrough, explain the path: "Start at Sheet X, look at [region], then see Sheet Y for [details]"
4. Use construction terminology appropriately
5. If information is missing or unclear, say so honestly
6. Keep responses concise but complete

Format your response with:
- Direct answer first
- Supporting details with sheet references
- Any relevant warnings or considerations
- Suggested next steps if applicable
```

---

## Implementation Notes

**JSON Output:**
All Gemini prompts use `response_mime_type: "application/json"` for guaranteed JSON output.

**Token Limits:**
- Pass 1: ~2000 tokens output max
- Pass 2: ~1000 tokens output max  
- Pass 3: ~1500 tokens output max
- Pointer analysis: ~500 tokens output max

**Error Handling:**
- Retry with exponential backoff on rate limits
- Store raw responses for debugging
- Log token usage to `usage_events` table for billing

**Model Selection:**
- Gemini 2.0 Flash for extraction (fast, cheap, good at structured output)
- Claude for query responses (better reasoning, more natural language)
