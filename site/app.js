/* AWS Radar front end. Plain JS, no build step. Data comes from data/index.js
   (window.RADAR_INDEX), lazily loaded data/s/<service>.js files (RADAR_LOAD) and, on first
   search, data/search.js (window.RADAR_SEARCH).

   Routes:  #/                               home (services + latest)
            #/s/<id>?k=launch,api&t=GA&m=1   service page with filters (shareable)
            #/search?q=<text>                full-history search
            #/sources                        source health */
(() => {
  "use strict";

  const IDX = window.RADAR_INDEX;
  const app = document.getElementById("app");
  if (!IDX) { app.innerHTML = '<p class="empty">No data yet. Run <code>uv run scripts/update.py</code>.</p>'; return; }

  const svcById = Object.fromEntries(IDX.services.map(s => [s.id, s]));
  const children = {};
  IDX.services.forEach(s => { if (s.parent) (children[s.parent] ||= []).push(s); });

  // ── source kinds (filter chips) ───────────────────────────────────────────
  const KINDS = [
    ["launch", "Launches"], ["api", "API changes"], ["roadmap", "Roadmaps"], ["blog", "Blogs"],
    ["ops", "Security & health"], ["media", "Video & audio"], ["community", "Community"], ["social", "Social"],
  ];
  const kindOf = (srcId) => {
    const g = IDX.sources[srcId]?.group;
    if (srcId === "botocore-changelog") return "api";
    if (srcId === "aws-blogs") return "blog";
    if (srcId === "aws-security-bulletins" || srcId === "aws-service-health") return "ops";
    if (g === "aws-official" || g === "aws-code") return "launch";
    if (g === "aws-roadmap") return "roadmap";
    if (g === "aws-media") return "media";
    return g || "community";
  };
  const SOURCE_LABEL = {
    "aws-whats-new": "What's New", "aws-blogs": "AWS Blogs", "aws-news-blog": "AWS News Blog",
    "botocore-changelog": "SDK API change", "reddit-aws": "Reddit", "hacker-news": "Hacker News",
    "bluesky-aws-people": "Bluesky", "aws-security-bulletins": "Security Bulletin",
    "aws-service-health": "Service Health", "last-week-in-aws": "Last Week in AWS",
    "aws-community-builders": "dev.to Community Builders", "x-following": "X",
  };
  const srcLabel = (id) => SOURCE_LABEL[id] || IDX.sources[id]?.name || id;
  const TAGS = ["GA", "preview", "region", "feature", "shipped", "coming-soon", "pricing", "deprecation", "security", "quota", "instances"];

  // ── helpers ───────────────────────────────────────────────────────────────
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("radar-" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("radar-" + k, JSON.stringify(v)); } catch (e) {} },
  };
  const fmtDay = (iso) => {
    const d = new Date(iso.length === 10 ? iso + "T12:00:00Z" : iso), today = new Date();
    const days = Math.floor((Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) -
                             Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
    const label = d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
    return days === 0 ? `Today · ${label}` : days === 1 ? `Yesterday · ${label}` : label;
  };
  const ago = (iso) => {
    if (!iso) return "never";
    const h = (Date.now() - new Date(iso)) / 36e5;
    return h < 1 ? "just now" : h < 24 ? `${Math.round(h)}h ago` : `${Math.round(h / 24)}d ago`;
  };
  const icon = (s, cls = "", lazy = true) => s?.icon
    ? `<img class="${cls}" src="${esc(s.icon)}" alt=""${lazy ? ' loading="lazy"' : ""}>`
    : `<span class="noicon ${cls}">${esc((s?.short || "?").slice(0, 3))}</span>`;
  const parseHash = () => {
    const [path, query = ""] = location.hash.replace(/^#/, "").split("?");
    return { path: path || "/", params: new URLSearchParams(query) };
  };
  const setQuery = (path, params) => {
    const q = params.toString();
    history.replaceState(null, "", `#${path}${q ? "?" + q : ""}`);
  };

  // ── watchlist ─────────────────────────────────────────────────────────────
  const watch = new Set(store.get("watch", []).filter(id => svcById[id]));
  const toggleWatch = (id) => { watch.has(id) ? watch.delete(id) : watch.add(id); store.set("watch", [...watch]); };
  const starBtn = (id) => `<button class="star ${watch.has(id) ? "on" : ""}" data-star="${esc(id)}" title="${watch.has(id) ? "Remove from" : "Add to"} watchlist" aria-pressed="${watch.has(id)}">${watch.has(id) ? "★" : "☆"}</button>`;

  // ── lazy data loading (script tags also work from file://) ────────────────
  const cache = {}, waiting = {};
  window.RADAR_LOAD = (id, items) => { cache[id] = items; (waiting[id] || []).forEach(f => f(items)); delete waiting[id]; };
  const loadScript = (src) => new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = src; s.onload = resolve; s.onerror = resolve;
    document.head.appendChild(s);
  });
  const loadService = (id) => new Promise((resolve) => {
    if (cache[id]) return resolve(cache[id]);
    if (!svcById[id]?.total && !svcById[id]?.mentions) return resolve([]);
    (waiting[id] ||= []).push(resolve);
    if (waiting[id].length > 1) return;
    loadScript(`data/s/${encodeURIComponent(id)}.js`).then(() => { if (!cache[id]) window.RADAR_LOAD(id, []); });
  });
  let searchLoad = null;
  const loadSearch = () => (searchLoad ||= loadScript("data/search.js").then(() => window.RADAR_SEARCH || []));

  // ── item list ─────────────────────────────────────────────────────────────
  function regionsHTML(rg) {
    if (!rg?.length) return "";
    const shown = rg.length <= 3 ? rg.join(", ") : `${rg.length} regions`;
    return `<span class="regions" title="${esc(rg.join(", "))}">${esc(shown)}</span>`;
  }

  function itemHTML(d, { showSvc }) {
    const svcs = d.svc.map(id => svcById[id]).filter(Boolean);
    const lead = svcs[0];
    const tags = d.tags.map(t => `<span class="tag ${esc(t)}">${esc(t)}</span>`).join("");
    const svcLinks = showSvc ? svcs.slice(0, 4).map(s => `<a class="svc-link" href="#/s/${esc(s.id)}">${esc(s.short)}</a>`).join(" · ") : "";
    const extra = [
      d.by && `<span>${esc(d.by)}</span>`,
      d.pts != null && `<span>${d.pts} pts</span>`,
      d.hn && d.hn !== d.u && `<a href="${esc(d.hn)}" target="_blank" rel="noopener">discussion</a>`,
      d.link && `<a href="${esc(d.link)}" target="_blank" rel="noopener">link</a>`,
    ].filter(Boolean).join(" · ");
    return `<li class="item ${showSvc ? "" : "bare"}">
      ${showSvc ? icon(lead, "svc-ico") : ""}
      <div>
        <a class="t" href="${esc(d.u)}" target="_blank" rel="noopener">${d.api ? `<span class="api">${esc(d.api)}</span>` : ""}${esc(d.t)}</a>
        ${d.s ? `<div class="s">${esc(d.s)}</div>` : ""}
        <div class="row">${tags}${regionsHTML(d.rg)}${svcLinks ? `<span>${svcLinks}</span>` : ""}<span>${esc(srcLabel(d.src))}</span>${extra ? `<span>${extra}</span>` : ""}</div>
      </div>
    </li>`;
  }

  function renderFeed(el, items, { showSvc, pageSize = 80 }) {
    let shown = 0, lastDay = null;
    el.innerHTML = "";
    if (!items.length) { el.innerHTML = '<p class="empty" style="padding:16px">Nothing matches these filters.</p>'; return; }
    const ul = document.createElement("ul");
    ul.className = "feed";
    el.appendChild(ul);
    const more = document.createElement("button");
    more.className = "more";
    const page = () => {
      const html = [];
      for (const d of items.slice(shown, shown + pageSize)) {
        const day = d.d.slice(0, 10);
        if (day !== lastDay) { html.push(`<li class="day">${esc(fmtDay(d.d))}</li>`); lastDay = day; }
        html.push(itemHTML(d, { showSvc }));
      }
      ul.insertAdjacentHTML("beforeend", html.join(""));
      shown += pageSize;
      more.hidden = shown >= items.length;
      more.textContent = `Show more (${items.length - shown} left)`;
    };
    more.onclick = page;
    el.appendChild(more);
    page();
  }

  function chipRow(options, active, onPick, counts = {}) {
    const row = document.createElement("div");
    row.className = "chips";
    row.innerHTML = options.map(([k, label]) =>
      `<button class="chip ${active.has(k) ? "on" : ""}" data-k="${esc(k)}">${esc(label)}${counts[k] != null ? `<span class="n">${counts[k]}</span>` : ""}</button>`).join("");
    row.onclick = (e) => { const b = e.target.closest(".chip"); if (b) onPick(b.dataset.k); };
    return row;
  }
  const toggleIn = (set, k, all = "all") => {
    if (k === all) { set.clear(); set.add(all); return; }
    set.delete(all);
    set.has(k) ? set.delete(k) : set.add(k);
    if (!set.size) set.add(all);
  };
  const setFrom = (param) => new Set(param ? param.split(",").filter(Boolean) : ["all"]);
  const setTo = (set) => set.has("all") ? "" : [...set].join(",");

  // ── home ──────────────────────────────────────────────────────────────────
  const home = {
    sort: store.get("sort", "active"),
    cats: new Set(["all"]),
    quiet: store.get("quiet", false),
    kinds: new Set(store.get("kinds", ["launch", "api"])),
    watchOnly: store.get("watchOnly", false),
  };

  function renderHome() {
    document.title = "AWS Radar";
    app.innerHTML = `<div class="home">
      <section class="panel" id="svc-panel"></section>
      <section class="panel" id="latest-panel"></section>
    </div>`;
    drawServices();
    drawLatest();
  }

  const tileHTML = (s) => `<a class="tile ${s.n30 ? "" : "quiet"}" href="#/s/${esc(s.id)}" title="${esc(s.name)}">
      ${s.n7 ? '<span class="dot" title="updates in the last 7 days"></span>' : ""}
      ${icon(s)}<div><div class="name">${esc(s.short)}</div>
      <div class="sub" title="${s.n30} updates in 30 days, ${s.l30} of them launches or API changes">${s.n30 ? `${s.n30} in 30d${s.l30 ? ` · ${s.l30}★` : ""}` : `last ${ago(s.last)}`}</div></div></a>`;

  function drawServices() {
    const el = document.getElementById("svc-panel");
    const visible = IDX.services.filter(s => !s.parent && (home.quiet || s.n30 > 0));
    const catCounts = {};
    visible.forEach(s => { catCounts[s.cat] = (catCounts[s.cat] || 0) + 1; });
    const cats = Object.entries(IDX.categories).filter(([k]) => catCounts[k]).sort((a, b) => a[1].name.localeCompare(b[1].name));
    el.innerHTML = `<div class="panel-head"><h2>Services</h2>
      <span class="meta" style="margin:0">${visible.length} ${home.quiet ? "" : "active in 30 days"}</span>
      <span class="spacer"></span>
      <label class="toggle"><input type="checkbox" id="quiet" ${home.quiet ? "checked" : ""}> show quiet</label>
      <div class="seg"><button data-s="active" class="${home.sort === "active" ? "on" : ""}">Most active</button><button data-s="cat" class="${home.sort === "cat" ? "on" : ""}">By category</button></div>
    </div>`;
    if (watch.size) {
      const w = document.createElement("div");
      w.className = "cat-block watch-block";
      const ws = [...watch].map(id => svcById[id]).sort((a, b) => a.short.localeCompare(b.short));
      w.innerHTML = `<div class="cat-title">★ Watchlist</div><div class="grid">${ws.map(tileHTML).join("")}</div>`;
      el.appendChild(w);
    }
    el.appendChild(chipRow([["all", "All"], ...cats.map(([k, c]) => [k, c.name])], home.cats, (k) => { toggleIn(home.cats, k); drawServices(); }, catCounts));
    const list = visible.filter(s => home.cats.has("all") || home.cats.has(s.cat));
    const body = document.createElement("div");
    if (home.sort === "active") {
      list.sort((a, b) => b.n30 - a.n30 || b.n7 - a.n7 || a.short.localeCompare(b.short));
      body.innerHTML = `<div class="cat-block"><div class="grid" style="margin-top:10px">${list.map(tileHTML).join("")}</div></div>`;
    } else {
      body.innerHTML = cats.filter(([k]) => home.cats.has("all") || home.cats.has(k)).map(([k, c]) => {
        const ss = list.filter(s => s.cat === k).sort((a, b) => a.short.localeCompare(b.short));
        return ss.length ? `<div class="cat-block"><div class="cat-title">${c.icon ? `<img src="${esc(c.icon)}" alt="">` : ""}${esc(c.name)}</div><div class="grid">${ss.map(tileHTML).join("")}</div></div>` : "";
      }).join("");
    }
    if (!list.length) body.innerHTML = '<p class="empty" style="padding:16px">No services here.</p>';
    el.appendChild(body);
    el.querySelector("#quiet").onchange = (e) => { home.quiet = e.target.checked; store.set("quiet", home.quiet); drawServices(); };
    el.querySelectorAll(".seg button").forEach(b => b.onclick = () => { home.sort = b.dataset.s; store.set("sort", home.sort); drawServices(); });
  }

  function drawLatest() {
    const el = document.getElementById("latest-panel");
    const base = home.watchOnly && watch.size ? IDX.latest.filter(d => d.svc.some(s => watch.has(s))) : IDX.latest;
    const counts = {};
    base.forEach(d => { const k = kindOf(d.src); counts[k] = (counts[k] || 0) + 1; });
    const items = base.filter(d => home.kinds.has("all") || home.kinds.has(kindOf(d.src)));
    el.innerHTML = `<div class="panel-head"><h2>Latest</h2>
      <span class="meta" style="margin:0">last 7 days</span>
      <span class="spacer"></span>
      ${watch.size ? `<label class="toggle"><input type="checkbox" id="watchonly" ${home.watchOnly ? "checked" : ""}> watchlist only</label>` : ""}
      <a class="feedlink" href="feeds/launches.xml" title="Atom feed: launches and API changes, all services">feed</a></div>`;
    el.appendChild(chipRow([["all", "All"], ...KINDS], home.kinds, (k) => { toggleIn(home.kinds, k); store.set("kinds", [...home.kinds]); drawLatest(); }, counts));
    const box = document.createElement("div");
    el.appendChild(box);
    renderFeed(box, items, { showSvc: true });
    el.querySelector("#watchonly")?.addEventListener("change", (e) => { home.watchOnly = e.target.checked; store.set("watchOnly", home.watchOnly); drawLatest(); });
  }

  // ── service page ──────────────────────────────────────────────────────────
  function activitySVG(items, id) {
    // Weekly counts for the last 26 weeks: launches + API changes + roadmap vs everything else.
    const weeks = 26, now = Date.now(), wk = 7 * 864e5;
    const a = new Array(weeks).fill(0), b = new Array(weeks).fill(0);
    for (const d of items) {
      if (!d.svc.includes(id)) continue;
      const i = weeks - 1 - Math.floor((now - new Date(d.d)) / wk);
      if (i < 0 || i >= weeks) continue;
      const k = kindOf(d.src);
      (k === "launch" || k === "api" || k === "roadmap") ? a[i]++ : b[i]++;
    }
    const max = Math.max(1, ...a.map((x, i) => x + b[i]));
    const W = 8, G = 3, H = 44;
    const bars = a.map((x, i) => {
      const ha = Math.round(x / max * H), hb = Math.round(b[i] / max * H), xpos = i * (W + G);
      const wkStart = new Date(now - (weeks - i) * wk).toISOString().slice(0, 10);
      return `<g><title>Week of ${wkStart}: ${x} launches/API, ${b[i]} other</title>
        <rect x="${xpos}" y="${H - ha - hb}" width="${W}" height="${hb}" rx="1.5" class="bar-b"/>
        <rect x="${xpos}" y="${H - ha}" width="${W}" height="${ha}" rx="1.5" class="bar-a"/></g>`;
    }).join("");
    return `<div class="activity"><svg viewBox="0 0 ${weeks * (W + G)} ${H}" width="${weeks * (W + G)}" height="${H}" role="img" aria-label="Weekly activity, last 26 weeks">${bars}</svg>
      <div class="legend"><span class="sw a"></span>launches + API <span class="sw b"></span>other · 26 weeks</div></div>`;
  }

  async function renderService(id, params) {
    const s = svcById[id];
    if (!s) { app.innerHTML = `<p class="empty">Unknown service “${esc(id)}”. <a href="#/">Back</a></p>`; return; }
    document.title = `${s.short} · AWS Radar`;
    const cat = IDX.categories[s.cat];
    const kids = children[id] || [];
    const parent = s.parent && svcById[s.parent];
    app.innerHTML = `<a class="back" href="#/">← All services</a>
      <div class="svc-head">${icon(s)}<div><h1>${esc(s.name)} ${starBtn(id)}</h1>
        <div class="sub">${esc(cat?.name || s.cat)}${parent ? ` · part of <a href="#/s/${esc(parent.id)}">${esc(parent.short)}</a>` : ""} · last update ${ago(s.last)}
        ${s.total ? ` · <a class="feedlink" href="feeds/s/${esc(id)}.xml" title="Atom feed for ${esc(s.short)}">feed</a>` : ""}</div></div>
        <div id="activity" class="activity-slot"></div>
        <div class="stats">
          <div class="stat"><b>${s.n7}</b><span>last 7 days</span></div>
          <div class="stat"><b>${s.n30}</b><span>last 30 days</span></div>
          <div class="stat"><b>${s.l30}</b><span>launch + API, 30d</span></div>
        </div></div>
      ${kids.length ? `<div class="related">Includes: ${kids.map(k => `<a class="chip" href="#/s/${esc(k.id)}">${esc(k.short)}</a>`).join("")}</div>` : ""}
      <section class="panel" id="svc-feed"><p class="empty" style="padding:16px">Loading…</p></section>`;
    const items = await loadService(id);
    if (parseHash().path !== `/s/${id}`) return;
    document.getElementById("activity").innerHTML = items.length ? activitySVG(items, id) : "";
    const st = {
      kinds: setFrom(params.get("k")), tags: setFrom(params.get("t")),
      mentions: params.has("m") ? params.get("m") === "1" : store.get("mentions", false),
    };
    const panel = document.getElementById("svc-feed");
    const draw = () => {
      const p = new URLSearchParams();
      if (setTo(st.kinds)) p.set("k", setTo(st.kinds));
      if (setTo(st.tags)) p.set("t", setTo(st.tags));
      if (st.mentions) p.set("m", "1");
      setQuery(`/s/${id}`, p);
      const pool = items.filter(d => st.mentions || d.svc.includes(id));
      const kc = {}, tc = {};
      pool.forEach(d => { const k = kindOf(d.src); kc[k] = (kc[k] || 0) + 1; d.tags.forEach(t => { tc[t] = (tc[t] || 0) + 1; }); });
      const list = pool.filter(d => (st.kinds.has("all") || st.kinds.has(kindOf(d.src))) &&
                                    (st.tags.has("all") || d.tags.some(t => st.tags.has(t))));
      const nMentions = items.length - items.filter(d => d.svc.includes(id)).length;
      panel.innerHTML = `<div class="panel-head"><h2>Updates</h2><span class="meta" style="margin:0">${list.length} of ${pool.length}</span>
        <span class="spacer"></span>
        ${nMentions ? `<label class="toggle" title="Blog posts and threads that only tag or mention this service"><input type="checkbox" id="mentions" ${st.mentions ? "checked" : ""}> include ${nMentions} passing mentions</label>` : ""}</div>`;
      panel.appendChild(chipRow([["all", "All sources"], ...KINDS.filter(([k]) => kc[k])], st.kinds, (k) => { toggleIn(st.kinds, k); draw(); }, kc));
      const tagOpts = TAGS.filter(t => tc[t]).map(t => [t, t]);
      if (tagOpts.length) panel.appendChild(chipRow([["all", "All tags"], ...tagOpts], st.tags, (k) => { toggleIn(st.tags, k); draw(); }, tc));
      const box = document.createElement("div");
      panel.appendChild(box);
      renderFeed(box, list, { showSvc: false, pageSize: 120 });
      panel.querySelector("#mentions")?.addEventListener("change", (e) => { st.mentions = e.target.checked; store.set("mentions", st.mentions); draw(); });
    };
    draw();
  }

  // ── full-history search ───────────────────────────────────────────────────
  async function renderSearch(params) {
    const q = (params.get("q") || "").trim();
    document.title = `Search: ${q} · AWS Radar`;
    qInput.value = q;
    app.innerHTML = `<a class="back" href="#/">← Home</a><section class="panel" id="search-panel"><p class="empty" style="padding:16px">Searching all history…</p></section>`;
    const rows = await loadSearch();
    if (parseHash().path !== "/search") return;
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    const hits = rows.filter(r => {
      const hay = `${r[1]} ${r[3]} ${r[5]} ${r[6]}`.toLowerCase();
      return terms.every(t => hay.includes(t));
    }).map(r => ({ d: r[0], t: r[1], u: r[2], svc: r[3] ? r[3].split(" ") : [], src: r[4], api: r[5] || undefined, tags: r[6] ? r[6].split(" ") : [] }));
    const kinds = setFrom(params.get("k"));
    const panel = document.getElementById("search-panel");
    const draw = () => {
      const p = new URLSearchParams({ q });
      if (setTo(kinds)) p.set("k", setTo(kinds));
      setQuery("/search", p);
      const kc = {};
      hits.forEach(d => { const k = kindOf(d.src); kc[k] = (kc[k] || 0) + 1; });
      const list = hits.filter(d => kinds.has("all") || kinds.has(kindOf(d.src)));
      panel.innerHTML = `<div class="panel-head"><h2>“${esc(q)}”</h2><span class="meta" style="margin:0">${list.length} of ${rows.length.toLocaleString()} items, all history</span></div>`;
      panel.appendChild(chipRow([["all", "All sources"], ...KINDS.filter(([k]) => kc[k])], kinds, (k) => { toggleIn(kinds, k); draw(); }, kc));
      const box = document.createElement("div");
      panel.appendChild(box);
      renderFeed(box, list, { showSvc: true, pageSize: 100 });
    };
    draw();
  }

  // ── source health ─────────────────────────────────────────────────────────
  function renderSources() {
    document.title = "Sources · AWS Radar";
    const rows = Object.entries(IDX.sources).sort((a, b) => a[1].group.localeCompare(b[1].group) || a[1].name.localeCompare(b[1].name));
    const status = (s) => !s.enabled ? ["off", "disabled"] : s.error ? ["bad", "failing"] :
      !s.last_success ? ["warn", "never run"] : ["ok", "ok"];
    app.innerHTML = `<a class="back" href="#/">← Home</a>
      <section class="panel"><div class="panel-head"><h2>Sources</h2><span class="meta" style="margin:0">${rows.length} configured · data built ${ago(IDX.generated)}</span></div>
      <div class="table-wrap"><table class="sources">
        <thead><tr><th>Source</th><th>Group</th><th>Status</th><th>Last success</th><th>Newest item</th><th class="num">Items</th><th>Every</th></tr></thead>
        <tbody>${rows.map(([id, s]) => { const [cls, label] = status(s); return `<tr>
          <td>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)}<div class="sub">${esc(id)} · ${esc(s.type)}</div></td>
          <td>${esc(s.group)}</td>
          <td><span class="pill ${cls}" ${s.error ? `title="${esc(s.error)}"` : ""}>${label}</span></td>
          <td>${ago(s.last_success)}</td><td>${s.newest ? ago(s.newest) : "–"}</td>
          <td class="num">${s.items.toLocaleString()}</td><td>${esc(s.cadence || "")}</td></tr>`; }).join("")}
        </tbody></table></div>
      <p class="note">Configured in <a href="https://github.com/pfeilbr/aws-radar/blob/main/config/sources.yaml">config/sources.yaml</a>. Hover a failing status for the error.</p></section>`;
  }

  // ── search box: service suggestions, Enter searches all history ───────────
  const qInput = document.getElementById("q");
  const sugg = document.getElementById("suggest");
  let active = 0, matches = [];
  const score = (s, q) => {
    const a = s.short.toLowerCase(), b = s.name.toLowerCase(), c = s.id;
    if (a === q || c === q) return 0;
    if (a.startsWith(q) || c.startsWith(q)) return 1;
    if (b.includes(q)) return 2 + b.indexOf(q) / 100;
    return 9;
  };
  const drawSuggest = () => {
    const q = qInput.value.trim().toLowerCase();
    if (!q) { sugg.hidden = true; return; }
    matches = IDX.services.map(s => [score(s, q), s]).filter(([n]) => n < 9)
      .sort((x, y) => x[0] - y[0] || y[1].n30 - x[1].n30).slice(0, 8).map(([, s]) => s);
    active = Math.min(active, matches.length);
    sugg.innerHTML = matches.map((s, i) => `<li data-i="${i}" class="${i === active ? "active" : ""}">${icon(s, "", false)}<span>${esc(s.name)}</span><span class="hint">${s.n30 ? s.n30 + " in 30d" : ""}</span></li>`).join("")
      + `<li data-i="${matches.length}" class="${active === matches.length ? "active" : ""}"><span class="noicon">⌕</span><span>Search all updates for “${esc(qInput.value.trim())}”</span><span class="hint">Enter</span></li>`;
    sugg.hidden = false;
  };
  const pick = (i) => {
    sugg.hidden = true;
    if (i < matches.length) { location.hash = `#/s/${matches[i].id}`; qInput.value = ""; qInput.blur(); return; }
    location.hash = `#/search?q=${encodeURIComponent(qInput.value.trim())}`;
    qInput.blur();
  };
  qInput.addEventListener("input", () => { active = 0; drawSuggest(); });
  qInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { active = Math.min(active + 1, matches.length); drawSuggest(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); drawSuggest(); e.preventDefault(); }
    else if (e.key === "Enter") { if (qInput.value.trim()) pick(active); e.preventDefault(); }
    else if (e.key === "Escape") { sugg.hidden = true; qInput.blur(); }
  });
  sugg.addEventListener("mousedown", (e) => { const li = e.target.closest("li"); if (li) { e.preventDefault(); pick(+li.dataset.i); } });
  qInput.addEventListener("blur", () => setTimeout(() => { sugg.hidden = true; }, 100));
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== qInput) { e.preventDefault(); qInput.focus(); }
  });

  // Star buttons anywhere on the page.
  app.addEventListener("click", (e) => {
    const b = e.target.closest("[data-star]");
    if (!b) return;
    e.preventDefault();
    toggleWatch(b.dataset.star);
    b.outerHTML = starBtn(b.dataset.star);
  });

  // ── theme + header meta ───────────────────────────────────────────────────
  document.getElementById("theme").onclick = () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("radar-theme", root.dataset.theme); } catch (e) {}
  };
  const failing = Object.values(IDX.sources).filter(s => s.enabled && s.error).length;
  document.getElementById("meta").innerHTML =
    `${IDX.counts.items.toLocaleString()} items · updated ${ago(IDX.generated)} · <a href="#/sources">${failing ? `<span class="pill bad">${failing} source${failing > 1 ? "s" : ""} failing</span>` : "sources"}</a>`;

  // ── router ────────────────────────────────────────────────────────────────
  let lastPath = null;
  const route = () => {
    const { path, params } = parseHash();
    if (path !== lastPath) window.scrollTo(0, 0);
    lastPath = path;
    if (path !== "/search") qInput.value = "";
    const m = path.match(/^\/s\/([\w-]+)$/);
    if (m) renderService(m[1], params);
    else if (path === "/search" && params.get("q")) renderSearch(params);
    else if (path === "/sources") renderSources();
    else renderHome();
  };
  window.addEventListener("hashchange", route);
  route();
})();
