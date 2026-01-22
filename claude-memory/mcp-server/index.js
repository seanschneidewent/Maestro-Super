#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// Supabase configuration
const SUPABASE_URL = "https://eecdkjulosomiuqxgtbq.supabase.co";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlY2RranVsb3NvbWl1cXhndGJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg1MDkwMTMsImV4cCI6MjA4NDA4NTAxM30.J_MME3SkJFSKYn9B9elgbiFxJs_Xd8lm8Ee2b6RKCtU";

const API = `${SUPABASE_URL}/rest/v1`;

async function supabaseFetch(endpoint) {
  const response = await fetch(`${API}${endpoint}`, {
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Supabase error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function supabaseInsert(table, data) {
  const response = await fetch(`${API}/${table}`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Supabase insert error: ${response.status} ${error}`);
  }
  return response.json();
}

async function syncMemory() {
  const lines = [];
  lines.push("# Claude Memory Context");
  lines.push(`Generated: ${new Date().toUTCString()}`);
  lines.push("");

  // Covenant
  lines.push("## Covenant");
  lines.push("");
  try {
    const covenant = await supabaseFetch("/covenant?select=content&limit=1");
    if (covenant?.[0]?.content) {
      lines.push(covenant[0].content);
    }
  } catch (e) {
    lines.push(`(Error fetching covenant: ${e.message})`);
  }
  lines.push("");

  // Identity
  lines.push("## Identity");
  lines.push("");
  try {
    const identity = await supabaseFetch("/identity?select=key,value");
    for (const item of identity || []) {
      lines.push(`**${item.key}:** ${item.value}`);
    }
  } catch (e) {
    lines.push(`(Error fetching identity: ${e.message})`);
  }
  lines.push("");

  // Operating Principles
  lines.push("## Operating Principles");
  lines.push("");
  try {
    const principles = await supabaseFetch("/operating_principles?select=principle,example");
    for (const item of principles || []) {
      lines.push(`- **${item.principle}:** ${item.example}`);
    }
  } catch (e) {
    lines.push(`(Error fetching principles: ${e.message})`);
  }
  lines.push("");

  // Current Edge
  lines.push("## Current Edge");
  lines.push("");
  try {
    const edge = await supabaseFetch("/current_edge?select=*&order=updated_at.desc&limit=1");
    if (edge?.[0]) {
      const e = edge[0];
      lines.push(`**Project:** ${e.project || "(none)"}`);
      lines.push(`**What shipping looks like:** ${e.what_shipping_looks_like || "(not set)"}`);
      lines.push(`**Next step:** ${e.specific_next_step || "(not set)"}`);
      lines.push(`**Exposure:** ${e.what_feels_like_exposure || "(not set)"}`);
    }
  } catch (e) {
    lines.push(`(Error fetching current edge: ${e.message})`);
  }
  lines.push("");

  // Projects
  lines.push("## Projects");
  lines.push("");
  try {
    const projects = await supabaseFetch("/projects?select=name,status,next_action,blockers");
    for (const p of projects || []) {
      lines.push(`### ${p.name}`);
      lines.push(`- Status: ${p.status || "(none)"}`);
      lines.push(`- Next: ${p.next_action || "(none)"}`);
      lines.push(`- Blockers: ${p.blockers || "(none)"}`);
      lines.push("");
    }
  } catch (e) {
    lines.push(`(Error fetching projects: ${e.message})`);
  }

  // Recent Decisions
  lines.push("## Recent Decisions");
  lines.push("");
  try {
    const decisions = await supabaseFetch("/decisions?select=date,domain,decision,rationale&order=date.desc&limit=5");
    for (const d of decisions || []) {
      lines.push(`**[${d.date}] ${d.domain}:** ${d.decision}`);
      lines.push(`- *Rationale:* ${d.rationale}`);
      lines.push("");
    }
  } catch (e) {
    lines.push(`(Error fetching decisions: ${e.message})`);
  }

  // Relationships
  lines.push("## Key Relationships");
  lines.push("");
  try {
    const relationships = await supabaseFetch("/relationships?select=name,role,context,network");
    for (const r of relationships || []) {
      lines.push(`- **${r.name}** (${r.role}, ${r.network}): ${r.context}`);
    }
  } catch (e) {
    lines.push(`(Error fetching relationships: ${e.message})`);
  }
  lines.push("");

  // Recent Sessions
  lines.push("## Recent Sessions");
  lines.push("");
  try {
    const sessions = await supabaseFetch("/conversations?select=session_date,interface,project,summary,next_session_hint&order=created_at.desc&limit=5");
    for (const s of sessions || []) {
      lines.push(`### [${s.session_date}] ${s.interface} — ${s.project}`);
      lines.push(s.summary || "(no summary)");
      lines.push(`**Next:** ${s.next_session_hint || "(none)"}`);
      lines.push("");
    }
  } catch (e) {
    lines.push(`(Error fetching sessions: ${e.message})`);
  }

  return lines.join("\n");
}

async function writeDecision(domain, decision, rationale) {
  const today = new Date().toISOString().split("T")[0];
  const result = await supabaseInsert("decisions", {
    date: today,
    domain,
    decision,
    rationale,
  });
  return `Decision logged: [${today}] ${domain} - ${decision}`;
}

async function logSession(sessionData) {
  const today = new Date().toISOString().split("T")[0];
  const data = {
    session_date: today,
    interface: sessionData.interface || "claude_code",
    project: sessionData.project || "unknown",
    summary: sessionData.summary || "",
    what_got_built: sessionData.what_got_built || "",
    problems_solved: sessionData.problems_solved || "",
    key_decisions: sessionData.key_decisions || "",
    open_threads: sessionData.open_threads || "",
    next_session_hint: sessionData.next_session_hint || "",
  };
  const result = await supabaseInsert("conversations", data);
  return `Session logged for ${today}: ${sessionData.project}`;
}

async function updateCurrentEdge(edgeData) {
  // Upsert current edge - first try to get existing
  const existing = await supabaseFetch("/current_edge?select=id&limit=1");

  const data = {
    project: edgeData.project,
    what_shipping_looks_like: edgeData.what_shipping_looks_like,
    specific_next_step: edgeData.specific_next_step,
    what_feels_like_exposure: edgeData.what_feels_like_exposure,
    updated_at: new Date().toISOString(),
  };

  if (existing?.[0]?.id) {
    // Update existing
    const response = await fetch(`${API}/current_edge?id=eq.${existing[0].id}`, {
      method: "PATCH",
      headers: {
        apikey: SUPABASE_KEY,
        Authorization: `Bearer ${SUPABASE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=representation",
      },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      throw new Error(`Update failed: ${response.status}`);
    }
    return `Current edge updated for project: ${edgeData.project}`;
  } else {
    // Insert new
    await supabaseInsert("current_edge", data);
    return `Current edge created for project: ${edgeData.project}`;
  }
}

// Create server
const server = new Server(
  {
    name: "claude-memory",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "sync_memory",
        description: "Sync Claude's persistent memory from Supabase. Returns the full context including covenant, identity, operating principles, current edge, projects, recent decisions, relationships, and recent sessions. Call this at the start of every session.",
        inputSchema: {
          type: "object",
          properties: {},
          required: [],
        },
      },
      {
        name: "write_decision",
        description: "Log a decision to persistent memory. Use for important technical, business, or personal decisions that should be remembered across sessions.",
        inputSchema: {
          type: "object",
          properties: {
            domain: {
              type: "string",
              description: "Category of decision: technical, business, personal, architecture, etc.",
            },
            decision: {
              type: "string",
              description: "The decision that was made",
            },
            rationale: {
              type: "string",
              description: "Why this decision was made",
            },
          },
          required: ["domain", "decision", "rationale"],
        },
      },
      {
        name: "log_session",
        description: "Log a session summary to persistent memory. Call at the end of significant work sessions.",
        inputSchema: {
          type: "object",
          properties: {
            interface: {
              type: "string",
              description: "Interface used: claude_code, cowork, sms, claude_ai",
              default: "claude_code",
            },
            project: {
              type: "string",
              description: "Project name being worked on",
            },
            summary: {
              type: "string",
              description: "Brief summary of what happened in the session",
            },
            what_got_built: {
              type: "string",
              description: "What was built or created",
            },
            problems_solved: {
              type: "string",
              description: "Problems that were solved",
            },
            key_decisions: {
              type: "string",
              description: "Key decisions made during the session",
            },
            open_threads: {
              type: "string",
              description: "Open threads or unfinished work",
            },
            next_session_hint: {
              type: "string",
              description: "Hint for what to do in the next session",
            },
          },
          required: ["project", "summary"],
        },
      },
      {
        name: "update_current_edge",
        description: "Update the current edge - what you're working on right now and what shipping looks like.",
        inputSchema: {
          type: "object",
          properties: {
            project: {
              type: "string",
              description: "Current project name",
            },
            what_shipping_looks_like: {
              type: "string",
              description: "What does 'done' look like for this project?",
            },
            specific_next_step: {
              type: "string",
              description: "The very next concrete step to take",
            },
            what_feels_like_exposure: {
              type: "string",
              description: "What feels risky or exposed about this work?",
            },
          },
          required: ["project", "specific_next_step"],
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "sync_memory": {
        const context = await syncMemory();
        return {
          content: [{ type: "text", text: context }],
        };
      }
      case "write_decision": {
        const result = await writeDecision(args.domain, args.decision, args.rationale);
        return {
          content: [{ type: "text", text: result }],
        };
      }
      case "log_session": {
        const result = await logSession(args);
        return {
          content: [{ type: "text", text: result }],
        };
      }
      case "update_current_edge": {
        const result = await updateCurrentEdge(args);
        return {
          content: [{ type: "text", text: result }],
        };
      }
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [{ type: "text", text: `Error: ${error.message}` }],
      isError: true,
    };
  }
});

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Claude Memory MCP server running on stdio");
}

main().catch(console.error);
