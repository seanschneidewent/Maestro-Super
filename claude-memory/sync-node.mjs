const SUPABASE_URL = 'https://eecdkjulosomiuqxgtbq.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlY2RranVsb3NvbWl1cXhndGJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg1MDkwMTMsImV4cCI6MjA4NDA4NTAxM30.J_MME3SkJFSKYn9B9elgbiFxJs_Xd8lm8Ee2b6RKCtU';
const API = SUPABASE_URL + '/rest/v1';

async function fetchTable(endpoint) {
  const response = await fetch(API + endpoint, {
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: 'Bearer ' + SUPABASE_KEY,
      'Content-Type': 'application/json',
    },
  });
  if (!response.ok) throw new Error(response.status + ' ' + response.statusText);
  return response.json();
}

async function main() {
  console.log('# Claude Memory Context');
  console.log('Generated:', new Date().toUTCString());
  console.log('');

  console.log('## Covenant');
  try {
    const c = await fetchTable('/covenant?select=content&limit=1');
    if (c?.[0]?.content) console.log(c[0].content);
  } catch(e) { console.log('(Error:', e.message + ')'); }
  console.log('');

  console.log('## Identity');
  try {
    const items = await fetchTable('/identity?select=key,value');
    for (const i of items || []) console.log('**' + i.key + ':** ' + i.value);
  } catch(e) { console.log('(Error:', e.message + ')'); }
  console.log('');

  console.log('## Operating Principles');
  try {
    const items = await fetchTable('/operating_principles?select=principle,example');
    for (const i of items || []) console.log('- **' + i.principle + ':** ' + i.example);
  } catch(e) { console.log('(Error:', e.message + ')'); }
  console.log('');

  console.log('## Current Edge');
  try {
    const e = await fetchTable('/current_edge?select=*&order=updated_at.desc&limit=1');
    if (e?.[0]) {
      console.log('**Project:** ' + (e[0].project || '(none)'));
      console.log('**What shipping looks like:** ' + (e[0].what_shipping_looks_like || '(not set)'));
      console.log('**Next step:** ' + (e[0].specific_next_step || '(not set)'));
      console.log('**Exposure:** ' + (e[0].what_feels_like_exposure || '(not set)'));
    }
  } catch(e) { console.log('(Error:', e.message + ')'); }
  console.log('');

  console.log('## Projects');
  try {
    const items = await fetchTable('/projects?select=name,status,next_action,blockers');
    for (const p of items || []) {
      console.log('### ' + p.name);
      console.log('- Status: ' + (p.status || '(none)'));
      console.log('- Next: ' + (p.next_action || '(none)'));
      console.log('- Blockers: ' + (p.blockers || '(none)'));
    }
  } catch(e) { console.log('(Error:', e.message + ')'); }
  console.log('');

  console.log('## Recent Decisions');
  try {
    const items = await fetchTable('/decisions?select=date,domain,decision,rationale&order=date.desc&limit=5');
    for (const d of items || []) {
      console.log('**[' + d.date + '] ' + d.domain + ':** ' + d.decision);
      console.log('- *Rationale:* ' + d.rationale);
    }
  } catch(e) { console.log('(Error:', e.message + ')'); }
  console.log('');

  console.log('## Key Relationships');
  try {
    const items = await fetchTable('/relationships?select=name,role,context,network');
    for (const r of items || []) {
      console.log('- **' + r.name + '** (' + r.role + ', ' + r.network + '): ' + r.context);
    }
  } catch(e) { console.log('(Error:', e.message + ')'); }
  console.log('');

  console.log('## Recent Sessions');
  try {
    const items = await fetchTable('/conversations?select=session_date,interface,project,summary,next_session_hint&order=created_at.desc&limit=5');
    for (const s of items || []) {
      console.log('### [' + s.session_date + '] ' + s.interface + ' — ' + s.project);
      console.log(s.summary || '(no summary)');
      console.log('**Next:** ' + (s.next_session_hint || '(none)'));
    }
  } catch(e) { console.log('(Error:', e.message + ')'); }
}

main();
