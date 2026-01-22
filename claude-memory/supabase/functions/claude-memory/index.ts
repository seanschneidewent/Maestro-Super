import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

async function syncMemory() {
  const result: Record<string, any> = {};

  // Covenant
  const { data: covenant } = await supabase
    .from("covenant")
    .select("content")
    .limit(1);
  result.covenant = covenant?.[0]?.content || null;

  // Identity
  const { data: identity } = await supabase
    .from("identity")
    .select("key, value");
  result.identity = identity || [];

  // Operating Principles
  const { data: principles } = await supabase
    .from("operating_principles")
    .select("principle, example");
  result.operating_principles = principles || [];

  // Current Edge
  const { data: edge } = await supabase
    .from("current_edge")
    .select("*")
    .order("updated_at", { ascending: false })
    .limit(1);
  result.current_edge = edge?.[0] || null;

  // Projects
  const { data: projects } = await supabase
    .from("projects")
    .select("name, status, next_action, blockers");
  result.projects = projects || [];

  // Recent Decisions
  const { data: decisions } = await supabase
    .from("decisions")
    .select("date, domain, decision, rationale")
    .order("date", { ascending: false })
    .limit(5);
  result.decisions = decisions || [];

  // Relationships
  const { data: relationships } = await supabase
    .from("relationships")
    .select("name, role, context, network");
  result.relationships = relationships || [];

  // Recent Sessions
  const { data: sessions } = await supabase
    .from("conversations")
    .select("session_date, interface, project, summary, next_session_hint")
    .order("created_at", { ascending: false })
    .limit(5);
  result.sessions = sessions || [];

  return result;
}

async function writeDecision(domain: string, decision: string, rationale: string) {
  const today = new Date().toISOString().split("T")[0];
  const { data, error } = await supabase
    .from("decisions")
    .insert({ date: today, domain, decision, rationale })
    .select();

  if (error) throw error;
  return { success: true, date: today, domain, decision };
}

async function logSession(sessionData: any) {
  const today = new Date().toISOString().split("T")[0];
  const { data, error } = await supabase
    .from("conversations")
    .insert({
      session_date: today,
      interface: sessionData.interface || "claude_code",
      project: sessionData.project || "unknown",
      summary: sessionData.summary || "",
      what_got_built: sessionData.what_got_built || "",
      problems_solved: sessionData.problems_solved || "",
      key_decisions: sessionData.key_decisions || "",
      open_threads: sessionData.open_threads || "",
      next_session_hint: sessionData.next_session_hint || "",
    })
    .select();

  if (error) throw error;
  return { success: true, date: today, project: sessionData.project };
}

async function updateCurrentEdge(edgeData: any) {
  const { data: existing } = await supabase
    .from("current_edge")
    .select("id")
    .limit(1);

  const payload = {
    project: edgeData.project,
    what_shipping_looks_like: edgeData.what_shipping_looks_like,
    specific_next_step: edgeData.specific_next_step,
    what_feels_like_exposure: edgeData.what_feels_like_exposure,
    updated_at: new Date().toISOString(),
  };

  if (existing?.[0]?.id) {
    const { error } = await supabase
      .from("current_edge")
      .update(payload)
      .eq("id", existing[0].id);
    if (error) throw error;
    return { success: true, action: "updated", project: edgeData.project };
  } else {
    const { error } = await supabase
      .from("current_edge")
      .insert(payload);
    if (error) throw error;
    return { success: true, action: "created", project: edgeData.project };
  }
}

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  const url = new URL(req.url);
  const action = url.searchParams.get("action") || "sync";

  try {
    let result;

    if (req.method === "GET" && action === "sync") {
      result = await syncMemory();
    } else if (req.method === "POST") {
      const body = await req.json();

      switch (action) {
        case "write_decision":
          result = await writeDecision(body.domain, body.decision, body.rationale);
          break;
        case "log_session":
          result = await logSession(body);
          break;
        case "update_edge":
          result = await updateCurrentEdge(body);
          break;
        default:
          throw new Error(`Unknown action: ${action}`);
      }
    } else {
      throw new Error(`Invalid request: ${req.method} ${action}`);
    }

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }
});
