/* Страница матча: шапка со счётом, обзор событий, статистика, составы, форма, H2H. */
window.MatchPage = (function () {
  const $ = s => document.querySelector(s);
  const esc = UI.esc;
  let id = null, data = null, sub = "overview", timer = null;

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
    const lname = pick(m.league, "name");

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
      ["overview", "match.overview"],
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
    if (sub === "overview") box.innerHTML = renderOverview();
    if (sub === "events") box.innerHTML = renderEvents() + renderForm();
    if (sub === "stats") box.innerHTML = renderStats();
    if (sub === "lineups") box.innerHTML = renderLineups();
    if (sub === "h2h") box.innerHTML = renderH2H();
  }

  const ICONS = {
    goal: "⚽", penalty_goal: "⚽", own_goal: "⚽", missed_penalty: "✖",
    yellow: "", red: "", subst: "⇄", var: "V"
  };

  /* ---------------------------------------------------------------- вкладка «Матч»
     Порядок блоков повторяет Flashscore: сначала то, ради чего пришли с
     рекламы (коэффициенты и бонус), затем справка о матче, форма команд и
     таблица лиги. */
  const BOOKIE_SIGNUP = "https://formula55.tj/sign-up";
  /* Кнопки ведут на страницу этого матча у букмекера, если она известна,
     иначе — на регистрацию. */
  function bookieUrl() {
    return (data.odds && data.odds.url) || BOOKIE_SIGNUP;
  }

  function renderOverview() {
    return renderOdds() + renderBonus() + renderInfo() + renderForm() + renderStandings();
  }

  /* Реальных коэффициентов пока нет — показываем прочерки. Разметка уже
     рассчитана на цифры, так что подключение парсера вёрстки не изменит. */
  function renderOdds() {
    const o = data.odds || {};
    const cell = val => `
      <a class="odds__cell" href="${bookieUrl()}" target="_blank" rel="nofollow noopener sponsored">
        ${val == null ? "—" : esc(Number(val).toFixed(2))}
        <svg class="odds__ext" width="9" height="9" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>
      </a>`;
    return `<section class="card fade-in odds">
      <div class="card__head"><span class="card__title">${esc(t("odds.title"))}</span></div>
      <div class="odds__kind"><span class="odds__pill">1X2</span></div>
      <div class="odds__grid odds__grid--head">
        <span></span>
        <span>${esc(t("odds.home"))}</span><span>${esc(t("odds.draw"))}</span><span>${esc(t("odds.away"))}</span>
      </div>
      <div class="odds__grid">
        <a class="odds__bookie" href="${bookieUrl()}" target="_blank" rel="nofollow noopener sponsored">
          <img src="/static/img/formula55-mark.png" alt="FORMULA55">
        </a>
        ${cell(o.home)}${cell(o.draw)}${cell(o.away)}
      </div>
    </section>`;
  }

  function renderBonus() {
    return `<section class="card fade-in bonus">
      <div class="card__head"><span class="card__title">${esc(t("bonus.title"))}</span></div>
      <div class="bonus__wrap">
        <a class="bonus__row" href="${BOOKIE_SIGNUP}" target="_blank" rel="nofollow noopener sponsored">
          <span class="bonus__logo"><img src="/static/img/formula55-mark.png" alt="FORMULA55"></span>
          <span class="bonus__text">${esc(t("bonus.formula55"))}</span>
          <svg class="bonus__arrow" width="18" height="18" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 18l6-6-6-6"/></svg>
        </a>
      </div>
    </section>`;
  }

  function renderInfo() {
    const unknown = t("info.unknown");
    const venue = data.venue
      ? data.venue + (data.venue_city ? ` (${data.venue_city})` : "")
      : unknown;
    const cap = data.venue_capacity
      ? Number(data.venue_capacity).toLocaleString(Settings.locale())
      : unknown;
    const ICON = {
      "info.venue": '<path d="M3 21h18M5 21V8l7-4 7 4v13M9 21v-5h6v5"/>',
      "info.capacity": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/>',
      // свисток: круг с мундштуком — у Flashscore он же
      "info.referee": '<circle cx="9" cy="14" r="5.5"/><path d="M14 11.5l6.5-3.2a1 1 0 0 0 .5-.9V6a1 1 0 0 0-1-1h-6"/>',
    };
    const row = (label, value) => `<div class="minfo__row">
      <svg class="minfo__icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        ${ICON[label]}</svg>
      <span class="minfo__label">${esc(t(label))}</span>
      <span class="minfo__value">${esc(value)}</span>
    </div>`;
    return `<section class="card fade-in minfo">
      <div class="card__head"><span class="card__title">${esc(t("info.title"))}</span></div>
      <div class="minfo__body">
        ${row("info.venue", venue)}
        ${row("info.capacity", cap)}
        ${row("info.referee", data.referee || unknown)}
      </div>
    </section>`;
  }

  /* Таблица лиги прямо под матчем. Строки играющих команд подсвечены, чтобы
     взгляд сразу находил их среди двадцати. */
  function renderStandings() {
    const groups = data.standings || [];
    if (!groups.length) return "";
    // Сравниваем по названию, а не по id: один и тот же клуб приходит из двух
    // источников под разными id, и в таблице он может оказаться под «чужим».
    const here = new Set([data.home.name, data.away.name]);
    return groups.map(g => `<section class="card fade-in" style="margin-top:12px">
      <div class="card__head">
        <span class="card__title">${esc(t("league.standings"))}</span>
        ${g.group ? `<span class="league-block__count">${esc(g.group)}</span>` : ""}
      </div>
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr>
            <th class="c-rank">#</th><th class="l">${esc(t("tbl.team"))}</th>
            <th>${esc(t("tbl.played"))}</th>
            <th class="hide-sm">${esc(t("tbl.win"))}</th>
            <th class="hide-sm">${esc(t("tbl.draw"))}</th>
            <th class="hide-sm">${esc(t("tbl.lose"))}</th>
            <th>${esc(t("tbl.gd"))}</th><th class="c-pts">${esc(t("tbl.points"))}</th>
          </tr></thead>
          <tbody>${g.rows.map(r => `
            <tr class="${here.has(r.team) ? "is-here" : ""}" data-team="${r.team_id}">
              <td class="c-rank">${r.rank}</td>
              <td class="c-team"><div>${UI.logo(r.logo, "", tname(r, "team", "team_tg", "team_en"))}<span>${esc(tname(r, "team", "team_tg", "team_en"))}</span></div></td>
              <td>${r.played}</td>
              <td class="hide-sm">${r.win}</td>
              <td class="hide-sm">${r.draw}</td>
              <td class="hide-sm">${r.lose}</td>
              <td>${r.gd > 0 ? "+" + r.gd : r.gd}</td>
              <td class="c-pts">${r.points}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </section>`).join("");
  }

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
        ? `<div class="tl__player">${esc(tname(e.assist))}</div>
           <div class="tl__assist">↓ ${esc(tname(e.player))}</div>`
        : `<div class="tl__player">${esc(tname(e.player))}</div>
           ${e.assist.name ? `<div class="tl__assist">${esc(tname(e.assist))}</div>` : ""}
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
          <div class="pl__name">${esc(tname(p).split(" ").slice(-1)[0])}</div>
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
            <span class="bench__num">${p.number ?? ""}</span><span>${esc(tname(p))}</span>
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
    const col = (side, list) => `<div class="mform__col">
      <div class="mform__head">
        ${UI.logo(data[side].logo, "mform__logo", tname(data[side]))}
        <span class="mform__name">${esc(tname(data[side]))}</span>
      </div>
      <div class="form-row" style="margin-bottom:10px">
        ${list.map(x => `<span class="form-badge form-badge--${x.result}">${esc(tform(x.result))}</span>`).join("")}
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
