(() => {
  "use strict";

  const SH = "Asia/Shanghai";
  const COLUMN_ORDER = ["发射台", "Meme币", "GameFi", "NFT铸造", "DeFi协议", "AI代理", "基础设施", "其他"];
  const CHAIN_COLORS = {
    ETH: "#627eea",
    Solana: "#14f195",
    BSC: "#f0b90b",
    Base: "#0052ff",
    TRON: "#ff0013",
    比特币: "#f7931a",
    Bitcoin: "#f7931a",
  };

  const state = {
    projects: [],
    q: "",
    chain: "",
    category: "",
    view: "board", // board | grid
    selected: null,
  };

  const $ = (sel) => document.querySelector(sel);

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toShanghai(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      return new Intl.DateTimeFormat("zh-CN", {
        timeZone: SH,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(d).replace(/\//g, "-");
    } catch {
      return iso;
    }
  }

  function relativeTime(iso) {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return "";
    const diff = Date.now() - t;
    const m = Math.floor(diff / 60000);
    if (m < 1) return "刚刚";
    if (m < 60) return `${m} 分钟前`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} 小时前`;
    const d = Math.floor(h / 24);
    if (d < 7) return `${d} 天前`;
    return toShanghai(iso);
  }

  function catClass(cat) {
    const safe = String(cat || "").replace(/\s+/g, "");
    return `cat-${safe}`;
  }

  function filtered() {
    const q = state.q.trim().toLowerCase();
    return state.projects.filter((p) => {
      if (state.chain && p.chain !== state.chain) return false;
      if (state.category && p.category !== state.category) return false;
      if (!q) return true;
      const hay = [
        p.name,
        p.twitter_handle,
        p.chain,
        p.category,
        p.status,
        p.listing,
        p.summary_cn,
        p.summary_en,
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }

  function countBy(arr, key) {
    const m = new Map();
    for (const p of arr) {
      const k = p[key] || "未知";
      m.set(k, (m.get(k) || 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh"));
  }

  function uniqueSorted(arr, key) {
    return [...new Set(arr.map((p) => p[key] || "未知"))].sort((a, b) =>
      a.localeCompare(b, "zh")
    );
  }

  function fillSelect(el, values, allLabel) {
    const cur = el.value;
    el.innerHTML = `<option value="">${esc(allLabel)}</option>` +
      values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
    if ([...el.options].some((o) => o.value === cur)) el.value = cur;
  }

  function renderStats(all, shown) {
    const chains = countBy(all, "chain").slice(0, 8);
    const cats = countBy(all, "category").slice(0, 8);
    const stats = $("#stats");
    const bits = [
      `<div class="stat accent"><div class="k">项目总数</div><div class="v">${all.length}</div></div>`,
      `<div class="stat"><div class="k">当前显示</div><div class="v">${shown.length}</div></div>`,
    ];
    for (const [k, v] of chains) {
      bits.push(`<div class="stat"><div class="k">⛓ ${esc(k)}</div><div class="v">${v}</div></div>`);
    }
    for (const [k, v] of cats.slice(0, 5)) {
      bits.push(`<div class="stat"><div class="k">📁 ${esc(k)}</div><div class="v">${v}</div></div>`);
    }
    stats.innerHTML = bits.join("");
  }

  function renderFilterChips(all) {
    const wrap = $("#catChips");
    const cats = countBy(all, "category");
    const buttons = [
      `<button type="button" data-cat="" class="${state.category === "" ? "active" : ""}">全部类型</button>`,
    ];
    for (const [k, v] of cats) {
      buttons.push(
        `<button type="button" data-cat="${esc(k)}" class="${state.category === k ? "active" : ""}">${esc(k)} · ${v}</button>`
      );
    }
    wrap.innerHTML = buttons.join("");
    wrap.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.category = btn.dataset.cat || "";
        $("#cat").value = state.category;
        render();
      });
    });
  }

  function cardHTML(p, idx) {
    const name = esc(p.name || "未命名");
    const handle = p.twitter_handle ? `@${esc(p.twitter_handle)}` : "";
    const chain = esc(p.chain || "未知");
    const cat = p.category || "其他";
    const status = esc(p.status || "—");
    const listing = esc(p.listing || "—");
    const summary = esc(p.summary_cn || p.summary_en || "");
    const time = esc(relativeTime(p.date_iso));
    const abs = esc(toShanghai(p.date_iso));
    const x = p.x_url ? esc(p.x_url) : (p.twitter_handle ? `https://x.com/${esc(p.twitter_handle)}` : "");
    const fans = esc(p.fans || "");
    return `
<article class="card" data-idx="${idx}" role="button" tabindex="0">
  <div class="card-top">
    <div>
      <h3 class="card-title">${name}</h3>
      <div class="card-handle">${handle}</div>
    </div>
    <div class="card-time" title="${abs}">${time}</div>
  </div>
  <div class="badges">
    <span class="badge chain">⛓ ${chain}</span>
    <span class="badge cat ${esc(catClass(cat))}">${esc(cat)}</span>
    <span class="badge status">${status}</span>
    <span class="badge listing">开盘 ${listing}</span>
  </div>
  ${summary ? `<div class="summary">${summary}</div>` : ""}
  <div class="card-foot">
    ${x ? `<a class="x-link" href="${x}" target="_blank" rel="noopener" onclick="event.stopPropagation()">𝕏 打开</a>` : `<span></span>`}
    <span class="fans">${fans}</span>
  </div>
</article>`;
  }

  function bindCards(root, list) {
    root.querySelectorAll(".card").forEach((el) => {
      const open = () => {
        const i = Number(el.dataset.idx);
        state.selected = list[i];
        openDrawer(state.selected);
      };
      el.addEventListener("click", open);
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
    });
  }

  function renderBoard(list) {
    const main = $("#main");
    if (!list.length) {
      main.innerHTML = `<div class="empty"><h2>没有匹配的项目</h2><p>试试清空筛选或换个关键词</p></div>`;
      return;
    }

    if (state.view === "grid") {
      main.innerHTML = `<div class="grid">${list.map((p, i) => cardHTML(p, i)).join("")}</div>`;
      bindCards(main, list);
      return;
    }

    // Kanban by category
    const groups = new Map();
    for (const p of list) {
      const k = p.category || "其他";
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(p);
    }
    const keys = [
      ...COLUMN_ORDER.filter((k) => groups.has(k)),
      ...[...groups.keys()].filter((k) => !COLUMN_ORDER.includes(k)).sort((a, b) => a.localeCompare(b, "zh")),
    ];

    // flatten index map for drawer
    const flat = [];
    let html = `<div class="board">`;
    for (const key of keys) {
      const items = groups.get(key) || [];
      const start = flat.length;
      flat.push(...items);
      html += `<section class="column">
        <div class="column-head">
          <div class="title"><span class="badge cat ${esc(catClass(key))}">${esc(key)}</span></div>
          <span class="count">${items.length}</span>
        </div>
        <div class="column-body">
          ${items.map((p, i) => cardHTML(p, start + i)).join("")}
        </div>
      </section>`;
    }
    html += `</div>`;
    main.innerHTML = html;
    bindCards(main, flat);
  }

  function openDrawer(p) {
    if (!p) return;
    const drawer = $("#drawer");
    const backdrop = $("#backdrop");
    $("#drawerTitle").textContent = p.name || "项目详情";
    $("#drawerHandle").textContent = p.twitter_handle ? `@${p.twitter_handle}` : "";
    const body = $("#drawerBody");
    const rows = [
      ["链", p.chain],
      ["类型", p.category],
      ["状态", p.status],
      ["开盘", p.listing],
      ["时间 (Asia/Shanghai)", toShanghai(p.date_iso)],
      ["粉丝", p.fans],
      ["中文摘要", p.summary_cn],
      ["英文简介", p.summary_en],
      ["风险", p.risk],
      ["X", p.x_url ? `<a href="${esc(p.x_url)}" target="_blank" rel="noopener">${esc(p.x_url)}</a>` : ""],
      ["链接", (p.urls || []).map((u) => `<div><a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a></div>`).join("")],
    ];
    body.innerHTML = rows
      .filter(([, v]) => v)
      .map(
        ([label, value]) =>
          `<div class="section"><div class="label">${esc(label)}</div><div class="value">${typeof value === "string" && value.includes("<a ") ? value : esc(value)}</div></div>`
      )
      .join("");
    drawer.classList.add("open");
    backdrop.classList.add("open");
  }

  function closeDrawer() {
    $("#drawer").classList.remove("open");
    $("#backdrop").classList.remove("open");
    state.selected = null;
  }

  function render() {
    const all = state.projects;
    const list = filtered();
    fillSelect($("#chain"), uniqueSorted(all, "chain"), "全部链");
    fillSelect($("#cat"), uniqueSorted(all, "category"), "全部类型");
    $("#chain").value = state.chain;
    $("#cat").value = state.category;
    renderStats(all, list);
    renderFilterChips(all);
    renderBoard(list);
    const newest = all[0]?.date_iso ? toShanghai(all[0].date_iso) : "—";
    $("#metaLine").innerHTML = `共 <b>${all.length}</b> 个项目 · 最新推送 ${esc(newest)} · 时区 Asia/Shanghai`;
  }

  async function load() {
    const res = await fetch("data/projects.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`加载失败 HTTP ${res.status}`);
    const data = await res.json();
    if (!Array.isArray(data)) throw new Error("数据格式错误");
    state.projects = data
      .slice()
      .sort((a, b) => (b.message_id || 0) - (a.message_id || 0));
    render();
  }

  function wire() {
    $("#q").addEventListener("input", (e) => {
      state.q = e.target.value;
      render();
    });
    $("#chain").addEventListener("change", (e) => {
      state.chain = e.target.value;
      render();
    });
    $("#cat").addEventListener("change", (e) => {
      state.category = e.target.value;
      render();
    });
    document.querySelectorAll(".seg button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".seg button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.view = btn.dataset.view;
        render();
      });
    });
    $("#backdrop").addEventListener("click", closeDrawer);
    $("#closeDrawer").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeDrawer();
    });
  }

  wire();
  load().catch((err) => {
    $("#main").innerHTML = `<div class="empty"><h2>无法加载数据</h2><p>${esc(err.message)}。请确认 data/projects.json 存在，或用本地服务器打开。</p></div>`;
  });
})();
