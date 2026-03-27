/**
 * PapaCasper Free AI Tools Worker
 * Deployed to Cloudflare Workers (free tier: 100k req/day)
 *
 * What it does:
 *  - Serves a free "AI Prompt Pack Generator" tool
 *  - Captures email before delivering the result
 *  - Subscribes email to Ghost newsletter
 *  - Shows upsell to LemonSqueezy premium pack
 *
 * Deploy: wrangler deploy
 * Route:  tools.papacasper.com/*
 */

const GHOST_API_URL = "https://blog.papacasper.com";
// Polar.sh — best prompt pack for upsell
const PROMPT_PACK_URL = "https://buy.polar.sh/polar_cl_vq0VhOPlSo2wVSvZytwJR4iYvYhD4ioo3IRbp0j3K5H";
const STORE_URL = "https://polar.sh/papacasper";

export default {
  async fetch(request, env) {
    const GHOST_ADMIN_KEY = env.GHOST_ADMIN_KEY;
    const ANTHROPIC_API_KEY = env.ANTHROPIC_API_KEY;
    const url = new URL(request.url);

    if (request.method === "OPTIONS") return cors();

    if (url.pathname === "/" || url.pathname === "") {
      return html(homePage());
    }

    if (url.pathname === "/generate" && request.method === "POST") {
      return handleGenerate(request, ANTHROPIC_API_KEY, GHOST_ADMIN_KEY);
    }

    if (url.pathname === "/subscribe" && request.method === "POST") {
      return handleSubscribe(request, GHOST_ADMIN_KEY);
    }

    return new Response("Not found", { status: 404 });
  },
};

// ── Route handlers ────────────────────────────────────────────────

async function handleGenerate(request, anthropicKey, ghostKey) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400); }

  const { niche, email } = body;
  if (!niche) return json({ error: "niche required" }, 400);

  // Subscribe to Ghost newsletter if email provided
  if (email && email.includes("@")) {
    await subscribeGhost(email, ghostKey).catch(() => {});
  }

  // Generate 10 prompts using Claude Haiku (cheapest, plenty for this)
  const prompts = await generatePrompts(niche, anthropicKey);

  return json({ prompts, upsell: upsellData(niche) });
}

async function handleSubscribe(request, ghostKey) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400); }
  const { email } = body;
  if (!email) return json({ error: "email required" }, 400);
  await subscribeGhost(email, ghostKey);
  return json({ success: true });
}

// ── Core logic ────────────────────────────────────────────────────

async function generatePrompts(niche, anthropicKey) {
  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": anthropicKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "claude-haiku-4-5",
      max_tokens: 1024,
      messages: [{
        role: "user",
        content: `Generate 10 highly specific, immediately usable AI prompts for: ${niche}

Format as a JSON array of objects: [{"title": "...", "prompt": "..."}]
Each prompt should be practical and solve a real problem in this niche.
Return ONLY the JSON array, no other text.`,
      }],
    }),
  });

  const data = await resp.json();
  const text = data.content?.[0]?.text || "[]";
  try {
    return JSON.parse(text);
  } catch {
    // Try to extract JSON from the response
    const match = text.match(/\[[\s\S]*\]/);
    return match ? JSON.parse(match[0]) : [];
  }
}

async function subscribeGhost(email, ghostKey) {
  // Ghost Members API — add a free member
  const token = await ghostJWT(ghostKey);
  await fetch(`${GHOST_API_URL}/ghost/api/admin/members/`, {
    method: "POST",
    headers: {
      "Authorization": `Ghost ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      members: [{ email, subscribed: true }],
    }),
  });
}

async function ghostJWT(ghostKey) {
  const [id, secret] = ghostKey.split(":");
  // Minimal JWT for Ghost Admin API
  const now = Math.floor(Date.now() / 1000);
  const header = btoa(JSON.stringify({ alg: "HS256", kid: id, typ: "JWT" })).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const payload = btoa(JSON.stringify({ iat: now, exp: now + 300, aud: "/admin/" })).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const sigInput = `${header}.${payload}`;

  const key = await crypto.subtle.importKey(
    "raw",
    hexToBytes(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(sigInput));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${sigInput}.${sigB64}`;
}

function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes;
}

function upsellData(niche) {
  return {
    headline: `Get 50 More ${niche} Prompts + Templates`,
    description: "The full pack includes 50 tested prompts, 5 workflow templates, and a quick-start guide.",
    price: "$17",
    url: PROMPT_PACK_URL,
    cta: "Get the Full Pack — $17",
  };
}

// ── HTML ──────────────────────────────────────────────────────────

function homePage() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Free AI Prompt Generator — PapaCasper Tools</title>
  <meta name="description" content="Generate 10 free, immediately usable AI prompts for any niche. No signup required.">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #0f0f11; color: #e8e8e8; min-height: 100vh; }
    .container { max-width: 680px; margin: 0 auto; padding: 48px 24px; }
    h1 { font-size: 2rem; font-weight: 700; line-height: 1.2; margin-bottom: 12px; }
    h1 span { color: #7c3aed; }
    .subtitle { color: #9ca3af; margin-bottom: 36px; font-size: 1.05rem; }
    .card { background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 28px; margin-bottom: 24px; }
    label { display: block; font-size: 0.9rem; color: #9ca3af; margin-bottom: 8px; }
    input[type=text], input[type=email] {
      width: 100%; padding: 12px 16px; background: #09090b; border: 1px solid #3f3f46;
      border-radius: 8px; color: #e8e8e8; font-size: 1rem; outline: none;
    }
    input:focus { border-color: #7c3aed; }
    button {
      width: 100%; padding: 14px; background: #7c3aed; color: white; border: none;
      border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; margin-top: 16px;
      transition: background 0.2s;
    }
    button:hover { background: #6d28d9; }
    button:disabled { background: #3f3f46; cursor: not-allowed; }
    .disclaimer { font-size: 0.8rem; color: #52525b; margin-top: 10px; text-align: center; }
    #results { display: none; }
    .prompt-card { background: #09090b; border: 1px solid #27272a; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .prompt-title { font-weight: 600; margin-bottom: 6px; font-size: 0.95rem; }
    .prompt-text { color: #9ca3af; font-size: 0.9rem; line-height: 1.5; }
    .copy-btn { background: #27272a; border: none; color: #9ca3af; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; float: right; }
    .copy-btn:hover { background: #3f3f46; color: #e8e8e8; }
    .upsell { background: linear-gradient(135deg, #1e1b4b, #18181b); border: 1px solid #4c1d95; border-radius: 12px; padding: 28px; text-align: center; margin-top: 24px; }
    .upsell h3 { font-size: 1.3rem; margin-bottom: 8px; }
    .upsell p { color: #9ca3af; margin-bottom: 20px; }
    .upsell-btn { display: inline-block; padding: 14px 32px; background: #7c3aed; color: white; text-decoration: none; border-radius: 8px; font-weight: 600; }
    .loading { text-align: center; padding: 32px; color: #7c3aed; }
    .spinner { display: inline-block; width: 24px; height: 24px; border: 3px solid #3f3f46; border-top-color: #7c3aed; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
<div class="container">
  <h1>Free <span>AI Prompt</span> Generator</h1>
  <p class="subtitle">Get 10 powerful, ready-to-use AI prompts for any niche — instantly.</p>

  <div class="card" id="form-section">
    <label for="niche">What do you need prompts for?</label>
    <input type="text" id="niche" placeholder="e.g. freelance copywriting, Notion productivity, Python development..." />

    <label for="email" style="margin-top:16px">Email (get 10 more free prompts weekly)</label>
    <input type="email" id="email" placeholder="you@example.com (optional)" />

    <button id="generate-btn" onclick="generate()">Generate My Free Prompts →</button>
    <p class="disclaimer">No spam. Unsubscribe anytime. We hate spam too.</p>
  </div>

  <div id="loading" style="display:none" class="loading">
    <span class="spinner"></span> Generating your prompts...
  </div>

  <div id="results">
    <h2 style="margin-bottom:16px">Your 10 Free Prompts</h2>
    <div id="prompt-list"></div>
    <div class="upsell" id="upsell-box"></div>
  </div>
</div>

<script>
async function generate() {
  const niche = document.getElementById('niche').value.trim();
  const email = document.getElementById('email').value.trim();
  if (!niche) { alert('Please enter a niche or topic'); return; }

  document.getElementById('form-section').style.display = 'none';
  document.getElementById('loading').style.display = 'block';
  document.getElementById('results').style.display = 'none';

  try {
    const res = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ niche, email })
    });
    const data = await res.json();

    document.getElementById('loading').style.display = 'none';
    document.getElementById('results').style.display = 'block';

    const list = document.getElementById('prompt-list');
    list.innerHTML = '';
    (data.prompts || []).forEach((p, i) => {
      list.innerHTML += \`
        <div class="prompt-card">
          <div class="prompt-title">
            \${i+1}. \${p.title}
            <button class="copy-btn" onclick="copy(this, \\\`\${p.prompt.replace(/\`/g,"'")}\\\`)">Copy</button>
          </div>
          <div class="prompt-text">\${p.prompt}</div>
        </div>\`;
    });

    if (data.upsell) {
      const u = data.upsell;
      document.getElementById('upsell-box').innerHTML = \`
        <h3>Want 50 More + Templates?</h3>
        <p>\${u.description}</p>
        <a class="upsell-btn" href="\${u.url}" target="_blank">\${u.cta}</a>\`;
    }
  } catch(e) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('form-section').style.display = 'block';
    alert('Something went wrong. Please try again.');
  }
}

function copy(btn, text) {
  navigator.clipboard.writeText(text);
  btn.textContent = 'Copied!';
  setTimeout(() => btn.textContent = 'Copy', 2000);
}
</script>
</body>
</html>`;
}

// ── Helpers ───────────────────────────────────────────────────────

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

function html(content) {
  return new Response(content, {
    headers: { "Content-Type": "text/html;charset=UTF-8" },
  });
}

function cors() {
  return new Response(null, { status: 204, headers: corsHeaders() });
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}
