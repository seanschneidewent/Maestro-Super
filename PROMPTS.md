# AI Prompt Templates

Reference prompts for the three-pass processing pipeline.

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

```
A superintendent is asking about their construction project. Find the most relevant context pointers to answer their question.

Question: {query_text}
Available Context:
- Discipline Summaries: {discipline_contexts}
- Page Summaries: {page_contexts}
- Pointer Summaries: {pointer_summaries}

Return the IDs of the most relevant pointers (max 10) with relevance scores.
```

---

## Notes

- All prompts use `response_mime_type: "application/json"` for guaranteed JSON output
- Token limits vary by prompt complexity
- Retry with exponential backoff on rate limits
- Store raw responses for debugging
