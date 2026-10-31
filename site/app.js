/* AWS Radar front end. Plain JS, no build step. Data comes from data/index.js
   (window.RADAR_INDEX) and lazily loaded data/s/<service>.js files (RADAR_LOAD). */
(() => {
  "use strict";

  const IDX = window.RADAR_INDEX;
  const app = document.getElementById("app");
  if (!IDX) { app.innerHTML = '<p class="empty">No data yet. Run <code>uv run scripts/update.py</code>.</p>'; return; }

  const svcById = Object.fromEntries(IDX.services.map(s => [s.id, s]));
  const children = {};
  IDX.services.forEach(s => { if (s.parent) (children[s.parent] ||= []).push(s); });

  // Source -> kind, used by the filter chips.
  const KINDS = [
    ["launch", "Launches"], ["api", "API changes"], ["blog", "Blogs"], ["ops", "Security & health"],
    ["media", "Video & audio"], ["community", "Community"], ["social", "Social"],
  ];
  const kindOf = (srcId) => {
    const g = IDX.sources[srcId]?.group;
    if (srcId === "aws-whats-new" || srcId === "aws-news-blog") return "launch";
    if (srcId === "aws-blogs") return "blog";
    if (srcId === "aws-security-bulletins" || srcId === "aws-service-health") return "ops";
    if (g === "aws-code") return srcId === "botocore-changelog" ? "api" : "launch";
    if (g === "aws-media") return "media";
    return g || "community";
  };
  const SOURCE_LABEL = {
    "aws-whats-new": "What's New", "aws-blogs": "AWS Blogs", "aws-news-blog": "AWS News Blog",
    "botocore-changelog": "SDK API change", "reddit-aws": "Reddit", "hacker-news": "Hacker News",
    "bluesky-aws-people": "Bluesky", "aws-security-bulletins": "Security Bulletin",
    "aws-service-health": "Service Health", "last-week-in-aws": "Last Week in AWS",
    "aws-community-builders": "dev.to Community Builders",
  };
  const srcLabel = (id) => SOURCE_LABEL[id] || IDX.sources[id]?.name || id;

  // ── small helpers ────────────────────────────────────────────────────────
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("radar-" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("radar-" + k, JSON.stringify(v)); } catch (e) {} },
  };
  const fmtDay = (iso) => {
    const d = new Date(iso), today = new Date();
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

  // ── service data loading (script tags work from file:// too) ─────────────
  const cache = {}, waiting = {};
  window.RADAR_LOAD = (id, items) => { cache[id] = items; (waiting[id] || []).forEach(f => f(items)); delete waiting[id]; };
  const loadService = (id) => new Promise((resolve) => {
    if (cache[id]) return resolve(cache[id]);
    if (!svcById[id]?.total && !svcById[id]?.mentions) return resolve([]);
    (waiting[id] ||= []).push(resolve);
    if (waiting[id].length > 1) return;
    const s = document.createElement("script");
    s.src = `data/s/${encodeURIComponent(id)}.js`;
    s.onerror = () => window.RADAR_LOAD(id, []);
    document.head.appendChild(s);
  });

  // ── item list ────────────────────────────────────────────────────────────
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
        <div class="row">${tags}${svcLinks ? `<span>${svcLinks}</span>` : ""}<span>${esc(srcLabel(d.src))}</span>${extra ? `<span>${extra}</span>` : ""}</div>
      </div>
    </li>`;
  }

  function renderFeed(el, items, { showSvc, pageSize = 80 }) {
    let shown = 0;
    const ul = document.createElement("ul");
    ul.className = "feed";
    el.innerHTML = "";
    el.appendChild(ul);
    let lastDay = null;
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
    if (!items.length) el.innerHTML = '<p class="empty" style="padding:16px">Nothing matches these filters.</p>';
    else page();
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
  const TAGS = ["GA", "preview", "region", "feature", "pricing", "deprecation", "security", "quota", "instances"];

  // ── home ─────────────────────────────────────────────────────────────────
  const home = {
    sort: store.get("sort", "active"),
    cats: new Set(["all"]),
    quiet: store.get("quiet", false),
    kinds: new Set(store.get("kinds", ["launch", "api"])),
    query: "",
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
    el.appendChild(chipRow([["all", "All"], ...cats.map(([k, c]) => [k, c.name])], home.cats, (k) => { toggleIn(home.cats, k); drawServices(); }, catCounts));
    const list = visible.filter(s => home.cats.has("all") || home.cats.has(s.cat));
    const tile = (s) => `<a class="tile ${s.n30 ? "" : "quiet"}" href="#/s/${esc(s.id)}" title="${esc(s.name)}">
        ${s.n7 ? '<span class="dot" title="updates in the last 7 days"></span>' : ""}
        ${icon(s)}<div><div class="name">${esc(s.short)}</div>
        <div class="sub" title="${s.n30} updates in 30 days, ${s.l30} of them launches or API changes">${s.n30 ? `${s.n30} in 30d${s.l30 ? ` · ${s.l30}★` : ""}` : `last ${ago(s.last)}`}</div></div></a>`;
    const body = document.createElement("div");
    if (home.sort === "active") {
      list.sort((a, b) => b.n30 - a.n30 || b.n7 - a.n7 || a.short.localeCompare(b.short));
      body.innerHTML = `<div class="cat-block"><div class="grid" style="margin-top:10px">${list.map(tile).join("")}</div></div>`;
    } else {
      body.innerHTML = cats.filter(([k]) => home.cats.has("all") || home.cats.has(k)).map(([k, c]) => {
        const ss = list.filter(s => s.cat === k).sort((a, b) => a.short.localeCompare(b.short));
        return ss.length ? `<div class="cat-block"><div class="cat-title">${c.icon ? `<img src="${esc(c.icon)}" alt="">` : ""}${esc(c.name)}</div><div class="grid">${ss.map(tile).join("")}</div></div>` : "";
      }).join("");
    }
    if (!list.length) body.innerHTML = '<p class="empty" style="padding:16px">No services here.</p>';
    el.appendChild(body);
    el.querySelector("#quiet").onchange = (e) => { home.quiet = e.target.checked; store.set("quiet", home.quiet); drawServices(); };
    el.querySelectorAll(".seg button").forEach(b => b.onclick = () => { home.sort = b.dataset.s; store.set("sort", home.sort); drawServices(); });
  }

  function drawLatest() {
    const el = document.getElementById("latest-panel");
    const q = home.query.trim().toLowerCase();
    const base = q ? IDX.latest.filter(d => (d.t + " " + (d.s || "") + " " + (d.api || "")).toLowerCase().includes(q)) : IDX.latest;
    const counts = {};
    base.forEach(d => { const k = kindOf(d.src); counts[k] = (counts[k] || 0) + 1; });
    const items = base.filter(d => home.kinds.has("all") || home.kinds.has(kindOf(d.src)));
    el.innerHTML = `<div class="panel-head"><h2>${q ? `Updates matching “${esc(home.query)}”` : "Latest"}</h2>
      <span class="meta" style="margin:0">last 7 days · all services</span>
      ${q ? '<span class="spacer"></span><button class="chip" id="clearq">clear search</button>' : ""}</div>`;
    el.appendChild(chipRow([["all", "All"], ...KINDS], home.kinds, (k) => { toggleIn(home.kinds, k); store.set("kinds", [...home.kinds]); drawLatest(); }, counts));
    const box = document.createElement("div");
    el.appendChild(box);
    renderFeed(box, items, { showSvc: true });
    el.querySelector("#clearq")?.addEventListener("click", () => { home.query = ""; qInput.value = ""; drawLatest(); });
  }

  // ── service page ─────────────────────────────────────────────────────────
  async function renderService(id) {
    const s = svcById[id];
    if (!s) { app.innerHTML = `<p class="empty">Unknown service “${esc(id)}”. <a href="#/">Back</a></p>`; return; }
    document.title = `${s.short} · AWS Radar`;
    const cat = IDX.categories[s.cat];
    const kids = children[id] || [];
    const parent = s.parent && svcById[s.parent];
    app.innerHTML = `<a class="back" href="#/">← All services</a>
      <div class="svc-head">${icon(s)}<div><h1>${esc(s.name)}</h1>
        <div class="sub">${esc(cat?.name || s.cat)}${parent ? ` · part of <a href="#/s/${esc(parent.id)}">${esc(parent.short)}</a>` : ""} · last update ${ago(s.last)}</div></div>
        <div class="stats">
          <div class="stat"><b>${s.n7}</b><span>last 7 days</span></div>
          <div class="stat"><b>${s.n30}</b><span>last 30 days</span></div>
          <div class="stat"><b>${s.l30}</b><span>launch + API, 30d</span></div>
        </div></div>
      ${kids.length ? `<div class="related">Includes: ${kids.map(k => `<a class="chip" href="#/s/${esc(k.id)}">${esc(k.short)}</a>`).join("")}</div>` : ""}
      <section class="panel" id="svc-feed"><p class="empty" style="padding:16px">Loading…</p></section>`;
    const items = await loadService(id);
    if (location.hash !== `#/s/${id}`) return;
    const st = { kinds: new Set(["all"]), tags: new Set(["all"]), mentions: store.get("mentions", false) };
    const panel = document.getElementById("svc-feed");
    const draw = () => {
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

  // ── search box: service suggestions + full-text filter of Latest ─────────
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
      + `<li data-i="${matches.length}" class="${active === matches.length ? "active" : ""}"><span class="noicon">⌕</span><span>Search the last 7 days for “${esc(qInput.value.trim())}”</span><span class="hint">Enter</span></li>`;
    sugg.hidden = false;
  };
  const pick = (i) => {
    sugg.hidden = true;
    if (i < matches.length) { location.hash = `#/s/${matches[i].id}`; qInput.value = ""; qInput.blur(); return; }
    home.query = qInput.value;
    if (location.hash.startsWith("#/s/")) location.hash = "#/"; else drawLatest();
  };
  qInput.addEventListener("input", () => { active = 0; drawSuggest(); });
  qInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { active = Math.min(active + 1, matches.length); drawSuggest(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); drawSuggest(); e.preventDefault(); }
    else if (e.key === "Enter") { pick(active); e.preventDefault(); }
    else if (e.key === "Escape") { sugg.hidden = true; qInput.blur(); }
  });
  sugg.addEventListener("mousedown", (e) => { const li = e.target.closest("li"); if (li) { e.preventDefault(); pick(+li.dataset.i); } });
  qInput.addEventListener("blur", () => setTimeout(() => { sugg.hidden = true; }, 100));
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== qInput) { e.preventDefault(); qInput.focus(); }
  });

  // ── theme + header meta ──────────────────────────────────────────────────
  document.getElementById("theme").onclick = () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("radar-theme", root.dataset.theme); } catch (e) {}
  };
  document.getElementById("meta").textContent =
    `${IDX.counts.items.toLocaleString()} items · updated ${ago(IDX.generated)}`;

  // ── router ───────────────────────────────────────────────────────────────
  const route = () => {
    const m = location.hash.match(/^#\/s\/([\w-]+)/);
    window.scrollTo(0, 0);
    if (m) renderService(m[1]); else renderHome();
  };
  window.addEventListener("hashchange", route);
  route();
})();
