/* Страница матча: шапка со счётом, обзор событий, статистика, составы, форма, H2H. */
window.MatchPage = (function () {
  const $ = s => document.querySelector(s);
  const esc = UI.esc;
  let id = null, data = null, sub = "events", timer = null;

  async function load(silent) {
    if (!silent) $("#matchPage").innerHTML = UI.skeleton(4);
    try {
      data = await API.match(id);
      render();
    } catch (e) {
      $("#matchPage").innerHTML = UI.empty("empty.matches", null, "⚠️");
    }
  }

  function render() {
    const m = data;
    const live = UI.LIVE.has(m.status);
    document.title = `${tname(m.home)} — ${tname(m.away)} | Tajscore`;
    const lang = Settings.get().lang;
    const lname = lang === "tg" ? m.league.name_tg : m.league.name_ru;

    const minute = live
      ? (m.status === "HT" ? t("status.ht")
         : (m.elapsed != null ? m.elapsed + (m.extra_minute ? "+" + m.extra_minute : "") + "′" : t("status.live")))
      : t(m.status_key);

    const score = (m.phase === "scheduled")
      ? Settings.formatTime(m.timestamp)
      : `${m.goals.home ?? 0} : ${m.goals.away ?? 0}`;

    const sub2 = [];
    if (m.ht.home != null) sub2.push(`${t("match.ht")} ${m.ht.home}:${m.ht.away}`);
    if (m.pen.home != null) sub2.push(`${t("match.pens")} ${m.pen.home}:${m.pen.away}`);

    const tabs = [
      ["events", "match.events"],
      ["stats", "match.stats"],
      ["lineups", "match.lineups"],
      ["h2h", "match.h2h"]
    ];

    $("#matchPage").innerHTML = `
      <section class="mhero fade-in">
        <div class="mhero__top">
          ${UI.logo(m.league.logo, "", lname)}
          <a href="/league/${m.league.id}"><b>${esc(lname)}</b></a>
          ${m.round ? `<span class="muted">· ${esc(m.round)}</span>` : ""}
          <span class="muted" style="margin-left:auto">${esc(Settings.formatDate(m.timestamp, true))}</span>
        </div>
        <div class="mhero__main">
          <div class="mteam">
            ${UI.logo(m.home.logo, "", tname(m.home))}
            <div class="mteam__name">${esc(tname(m.home))}</div>
          </div>
          <div class="mscore">
            <div class="mscore__val${live ? " mscore__val--live" : ""}" id="heroScore">${esc(score)}</div>
            <div class="mscore__status${live ? " mscore__status--live" : ""}" id="heroStatus">
              ${live ? '<span class="match__pulse"></span>' : ""}${esc(minute)}
            </div>
            ${sub2.length ? `<div class="mscore__sub">${esc(sub2.join(" · "))}</div>` : ""}
          </div>
          <div class="mteam">
            ${UI.logo(m.away.logo, "", tname(m.away))}
            <div class="mteam__name">${esc(tname(m.away))}</div>
          </div>
        </div>
        ${(m.venue || m.referee) ? `<div class="card__foot">
          ${m.venue ? `${esc(t("match.venue"))}: ${esc(m.venue)}${m.venue_city ? ", " + esc(m.venue_city) : ""}` : ""}
          ${m.referee ? ` · ${esc(t("match.referee"))}: ${esc(m.referee)}` : ""}
        </div>` : ""}
      </section>

      <div class="subtabs" id="subtabs">
        ${tabs.map(([k, i]) => `<button class="subtab${sub === k ? " is-active" : ""}" data-sub="${k}">${esc(t(i))}</button>`).join("")}
      </div>
      <div id="subContent"></div>`;

    renderSub();
  }

  function renderSub() {
    const box = $("#subContent");
    if (sub === "events") box.innerHTML = renderEvents() + renderForm();
    if (sub === "stats") box.innerHTML = renderStats();
    if (sub === "lineups") box.innerHTML = renderLineups();
    if (sub === "h2h") box.innerHTML = renderH2H();
  }

  const ICONS = {
    goal: "⚽", penalty_goal: "⚽", own_goal: "⚽", missed_penalty: "✖",
    yellow: "", red: "", subst: "⇄", var: "V"
  };

  function renderEvents() {
    const evs = data.events;
    if (!evs.length) return `<div class="card">${UI.empty("empty.events", null, "📋")}</div>`;
    let html = `<div class="card fade-in"><div class="tl">`;
    let halfDone = false;
    evs.forEach(e => {
      if (!halfDone && e.minute > 45) { halfDone = true;
        html += `<div class="tl__break"><span>${esc(t("match.ht"))}</span></div>`; }
      const home = e.team_id === data.home.id;
      const min = (e.minute ?? "") + (e.extra ? "+" + e.extra : "") + "′";
      const detail = e.kind === "subst"
        ? `<div class="tl__player">${esc(e.assist.name || "")}</div>
           <div class="tl__assist">↓ ${esc(e.player.name || "")}</div>`
        : `<div class="tl__player">${esc(e.player.name || "")}</div>
           ${e.assist.name ? `<div class="tl__assist">${esc(e.assist.name)}</div>` : ""}
           ${e.kind === "own_goal" ? `<div class="tl__assist">${esc(t("stat.red", "автогол"))}</div>` : ""}`;
      const icon = `<span class="tl__icon tl__icon--${e.kind}">${ICONS[e.kind] || ""}</span>`;
      html += `<div class="tl__ev tl__ev--${e.kind}">
        ${home ? `<div class="tl__side tl__side--home"><div>${detail}</div>${icon}</div>` : `<div></div>`}
        <div class="tl__min">${esc(min)}</div>
        ${!home ? `<div class="tl__side tl__side--away">${icon}<div>${detail}</div></div>` : ""}
      </div>`;
    });
    return html + `</div></div>`;
  }

  function renderStats() {
    const st = data.statistics;
    if (!st.length) return `<div class="card">${UI.empty("empty.stats", null, "📊")}</div>`;
    const rows = st.map(s => {
      const hv = parseFloat(String(s.home ?? "0").replace("%", "")) || 0;
      const av = parseFloat(String(s.away ?? "0").replace("%", "")) || 0;
      const total = hv + av || 1;
      return `<div class="stat">
        <div class="stat__top">
          <span class="stat__num">${esc(s.home ?? "0")}</span>
          <span class="stat__name">${esc(s.i18n ? t(s.i18n) : s.key)}</span>
          <span class="stat__num stat__num--away">${esc(s.away ?? "0")}</span>
        </div>
        <div class="stat__bar">
          <div class="stat__fill stat__fill--home" style="width:${(hv / total * 100).toFixed(1)}%"></div>
          <div class="stat__fill stat__fill--away" style="width:${(av / total * 100).toFixed(1)}%"></div>
        </div>
      </div>`;
    }).join("");
    return `<div class="card fade-in" style="padding:6px 0">${rows}</div>`;
  }

  /* Расстановка по grid из API: "линия:позиция" */
  function pitchHalf(side, lineup) {
    const lines = {};
    lineup.start.forEach(p => {
      const row = (p.grid || "1:1").split(":")[0];
      (lines[row] = lines[row] || []).push(p);
    });
    const keys = Object.keys(lines).sort((a, b) => a - b);
    return `<div class="pitch__half pitch__half--${side}">
      ${keys.map(k => `<div class="pitch__line">
        ${lines[k].map(p => `<div class="pl pl--${side}">
          <div class="pl__num">${p.number ?? ""}</div>
          <div class="pl__name">${esc((p.name || "").split(" ").slice(-1)[0])}</div>
        </div>`).join("")}
      </div>`).join("")}
    </div>`;
  }

  function renderLineups() {
    const lu = data.lineups;
    if (!lu.home.start.length && !lu.away.start.length)
      return `<div class="card">${UI.empty("empty.lineups", null, "👥")}</div>`;
    return `<div class="card fade-in">
      <div class="card__head">
        <span class="card__title">${esc(tname(data.home))} ${esc(lu.home.formation || "")}</span>
        <span class="card__title" style="margin-left:auto">${esc(lu.away.formation || "")} ${esc(tname(data.away))}</span>
      </div>
      <div style="padding:12px">${`<div class="pitch">${pitchHalf("home", lu.home)}${pitchHalf("away", lu.away)}</div>`}</div>
      <div class="bench">
        ${["home", "away"].map(side => `<div class="bench__col">
          <div class="bench__title">${esc(t("match.bench"))} · ${esc(tname(data[side]))}</div>
          ${lu[side].bench.map(p => `<div class="bench__row">
            <span class="bench__num">${p.number ?? ""}</span><span>${esc(p.name)}</span>
            <span class="muted" style="margin-left:auto;font-size:11px">${esc(p.pos || "")}</span>
          </div>`).join("") || `<div class="muted" style="font-size:12px">—</div>`}
          ${lu[side].coach ? `<div class="bench__row" style="margin-top:8px;border-top:1px solid var(--border-soft);padding-top:8px">
            <span class="muted">${esc(t("match.coach"))}:</span> <b>${esc(lu[side].coach)}</b></div>` : ""}
        </div>`).join("")}
      </div>
    </div>`;
  }

  function renderForm() {
    const f = data.form;
    if (!f.home.length && !f.away.length) return "";
    const col = (side, list) => `<div style="padding:12px 14px">
      <div class="bench__title">${esc(tname(data[side]))}</div>
      <div class="form-row" style="margin-bottom:10px">
        ${list.map(x => `<span class="form-badge form-badge--${x.result}">${x.result}</span>`).join("")}
      </div>
      ${list.map(x => `<div class="match match--mini" data-match="${x.id}" style="padding:6px 0;border:0">
        <div class="match__time">${esc(Settings.formatDate(x.timestamp))}</div>
        <div class="match__teams" style="gap:2px">
          <div class="match__team"><span style="font-size:12px">${esc(tname(x.home))}</span></div>
          <div class="match__team"><span style="font-size:12px">${esc(tname(x.away))}</span></div>
        </div>
        <div class="match__score" style="font-size:12.5px"><div>${x.goals.home}</div><div>${x.goals.away}</div></div>
      </div>`).join("")}
    </div>`;
    return `<div class="card fade-in" style="margin-top:12px">
      <div class="card__head"><span class="card__title">${esc(t("match.form"))}</span></div>
      <div style="display:grid;grid-template-columns:1fr 1fr">${col("home", f.home)}${col("away", f.away)}</div>
    </div>`;
  }

  function renderH2H() {
    if (!data.h2h.length) return `<div class="card">${UI.empty("empty.matches", null, "🤝")}</div>`;
    return `<div class="card fade-in">
      <div class="card__head"><span class="card__title">${esc(t("match.h2h"))}</span></div>
      <div class="card__body">${data.h2h.map(m => UI.matchRow(m)).join("")}</div>
    </div>`;
  }

  function init(fixtureId) {
    id = fixtureId;
    document.addEventListener("click", e => {
      const b = e.target.closest("[data-sub]");
      if (!b) return;
      sub = b.dataset.sub;
      document.querySelectorAll(".subtab").forEach(x => x.classList.toggle("is-active", x === b));
      renderSub();
    });
    load();
    // живой матч — обновляем каждые 20 секунд
    timer = setInterval(() => {
      if (!document.hidden && data && UI.LIVE.has(data.status)) load(true);
    }, 20000);
    document.addEventListener("tajscore:settings", () => load(true));
  }

  return { init };
})();
