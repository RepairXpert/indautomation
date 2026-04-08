// RepairXpert IndAutomation — Service Worker for offline fault code lookup
// Field techs lose signal inside plants. This caches the fault database locally.

const CACHE_NAME = 'repairxpert-v1';
const FAULT_DATA_URL = '/api/faults-data';

// Static assets to cache on install
const PRECACHE_URLS = [
  '/static/style.css',
  '/static/icon.svg',
  '/static/logo.svg',
  '/faults',
];

// Install: precache static assets + fault database
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll([...PRECACHE_URLS, FAULT_DATA_URL]);
    }).then(() => self.skipWaiting())
  );
});

// Activate: clear old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch strategy
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  // Fault data API: network-first, fall back to cache
  if (url.pathname === '/api/faults-data') {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Fault index page: network-first, fall back to cache
  if (url.pathname === '/faults') {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Individual fault pages: network-first, synthesize from cached data if offline
  if (url.pathname.startsWith('/fault/')) {
    event.respondWith(handleFaultDetail(event.request, url));
    return;
  }

  // Chat page: network-first, show offline message if unavailable
  if (url.pathname === '/chat') {
    event.respondWith(handleChat(event.request));
    return;
  }

  // Everything else: network-first with cache fallback
  event.respondWith(networkFirst(event.request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response('Offline', { status: 503 });
  }
}

// Synthesize a fault detail page from cached JSON when offline
async function handleFaultDetail(request, url) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    // Try cached version of this exact page first
    const cached = await caches.match(request);
    if (cached) return cached;

    // Synthesize from cached fault data
    const faultData = await caches.match(FAULT_DATA_URL);
    if (!faultData) return offlinePage('Fault data not cached yet. Visit /faults while online first.');

    const data = await faultData.json();
    const code = url.pathname.replace('/fault/', '').toLowerCase();
    const entry = data.faults.find(f =>
      f.code && f.code.toLowerCase() === code
    ) || data.faults.find(f =>
      f.code && f.code.toLowerCase().includes(code)
    );

    if (!entry) return offlinePage('Fault code not found in cached database.');

    const steps = (entry.fix_steps || []).map((s, i) => `<li>${esc(s)}</li>`).join('');
    const causes = (entry.possible_causes || []).map(c => `<li>${esc(c)}</li>`).join('');
    const tricks = (entry.field_tricks || []).map(t => `<li>${esc(t)}</li>`).join('');

    const html = `<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(entry.code)} — ${esc(entry.name || '')} | RepairXpert (Offline)</title>
<link rel="stylesheet" href="/static/style.css">
<style>body{font-family:system-ui,sans-serif;background:#0a0a0f;color:#e8e8ed;padding:20px;max-width:800px;margin:0 auto}
.offline-badge{background:#f59e0b;color:#000;padding:4px 12px;border-radius:4px;font-size:13px;display:inline-block;margin-bottom:16px}
h1{font-size:24px;margin-bottom:8px}h2{font-size:18px;margin-top:24px;color:#3b82f6}
ul,ol{padding-left:20px;margin:8px 0}li{margin:4px 0}
.severity{padding:4px 8px;border-radius:4px;font-size:13px;font-weight:600}
.severity-high,.severity-critical{background:#ef4444;color:#fff}
.severity-medium{background:#f59e0b;color:#000}
.severity-low{background:#10b981;color:#fff}
a{color:#3b82f6}</style></head><body>
<span class="offline-badge">OFFLINE — Cached Data</span>
<h1>${esc(entry.code)}</h1>
<p><strong>${esc(entry.name || '')}</strong></p>
${entry.severity ? `<p>Severity: <span class="severity severity-${entry.severity.toLowerCase()}">${esc(entry.severity)}</span></p>` : ''}
${entry.equipment_type ? `<p>Equipment: ${esc(entry.equipment_type)}</p>` : ''}
${entry.description ? `<p>${esc(entry.description)}</p>` : ''}
${causes ? `<h2>Possible Causes</h2><ul>${causes}</ul>` : ''}
${steps ? `<h2>Fix Steps</h2><ol>${steps}</ol>` : ''}
${tricks ? `<h2>Field Tricks</h2><ul>${tricks}</ul>` : ''}
<p style="margin-top:24px"><a href="/faults">&larr; All Fault Codes</a></p>
</body></html>`;

    return new Response(html, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// Chat page offline handler
async function handleChat(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return offlinePage(
      `<h2>You're offline</h2>
       <p>AI chat requires an internet connection and is unavailable right now.</p>
       <p style="margin-top:16px"><strong>But your fault database is still available:</strong></p>
       <p><a href="/faults" style="color:#3b82f6;font-size:18px">&rarr; Browse ${''} Fault Codes</a></p>
       <p style="margin-top:12px;color:#7a7a8e">The full fault code database was cached on your last online visit. You can look up any code, see causes, fix steps, and field tricks — no signal needed.</p>`
    );
  }
}

function offlinePage(content) {
  const html = `<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline | RepairXpert</title>
<link rel="stylesheet" href="/static/style.css">
<style>body{font-family:system-ui,sans-serif;background:#0a0a0f;color:#e8e8ed;padding:40px 20px;max-width:600px;margin:0 auto;text-align:center}
h2{color:#f59e0b;margin-bottom:12px}a{color:#3b82f6}</style></head>
<body>${content}</body></html>`;
  return new Response(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
