/* Рендеринг общих блоков: строки матчей, группы лиг, заглушки, скелетоны. */
window.UI = (function () {

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const LIVE = new Set(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);
  const DONE = new Set(["FT", "AET", "PEN"]);

  function logo(url, cls, alt) {
    if (!url) return `<span class="${cls}" style="background:var(--surface-3);border-radius:4px"></span>`;
    return `<img class="${cls}" src="${esc(url)}" alt="${esc(alt || "")}" loading="lazy" onerror="this.style.visibility='hidden'">`;
  }

  /* Левая колонка времени: часы, минута матча или «Финал» */
  function timeCell(m, opts) {
    if (LIVE.has(m.status)) {
      // «Перерыв» / «Танаффус» — слово, а не минута: свой класс, иначе оно
      // вылезает из узкой колонки и получает штрих минуты от ::after
      if (m.status === "HT") return `<div class="match__time match__time--live match__time--word">
        <span class="match__pulse"></span>${esc(t("status.short.ht"))}</div>`;
      const min = m.elapsed != null ? m.elapsed + (m.extra_minute ? "+" + m.extra_minute : "") : "";
      return `<div class="match__time match__time--live"><span class="match__pulse"></span>${esc(min)}</div>`;
    }
    if (DONE.has(m.status)) {
      return `<div class="match__time">${esc(Settings.formatTime(m.timestamp))}
        <span class="match__status-txt">${esc(t("status.short.ft"))}</span></div>`;
    }
    if (["PST", "CANC", "ABD", "AWD", "WO", "TBD"].includes(m.status)) {
      return `<div class="match__time"><span class="match__status-txt">${esc(t(m.status_key))}</span></div>`;
    }
    // В «Популярном» матч не на сегодня показываем датой, иначе часы выглядят как сегодняшние
    if (opts && opts.showDate && !Settings.isToday(m.timestamp)) {
      return `<div class="match__time">${esc(Settings.formatDayMonth(m.timestamp))}</div>`;
    }
    return `<div class="match__time">${esc(Settings.formatTime(m.timestamp))}</div>`;
  }

  function scoreCell(m) {
    const live = LIVE.has(m.status);
    const played = live || DONE.has(m.status);
    if (!played) return `<div class="match__score match__score--pending"><div>–</div><div>–</div></div>`;
    const cls = live ? "match__score match__score--live" : "match__score";
    const hw = m.winner === "home", aw = m.winner === "away";
    return `<div class="${cls}" data-score>
      <div data-side="home" style="${hw ? "" : aw ? "opacity:.62" : ""}">${m.goals.home ?? 0}</div>
      <div data-side="away" style="${aw ? "" : hw ? "opacity:.62" : ""}">${m.goals.away ?? 0}</div>
    </div>`;
  }

  function teamRow(team, side, m) {
    const done = DONE.has(m.status);
    const name = tname(team);
    let cls = "match__team";
    if (done && m.winner) cls += m.winner === side ? " match__team--winner" : " match__team--loser";
    return `<div class="${cls}">${logo(team.logo, "", name)}<span>${esc(name || "—")}</span></div>`;
  }

  const starSvg = on => `<svg width="14" height="14" viewBox="0 0 24 24" fill="${on ? "currentColor" : "none"}"
      stroke="currentColor" stroke-width="1.9" stroke-linejoin="round">
      <path d="m12 3.6 2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.7l5.8-.8z"/></svg>`;

  function matchRow(m, opts) {
    opts = opts || {};
    const live = LIVE.has(m.status);
    const fav = Settings.isFavMatch(m.id);
    const cls = "match" + (live ? " is-live" : "") + (opts.mini ? " match--mini" : "");
    // --j задаёт задержку каскада внутри блока лиги (см. .league-block .match в CSS)
    const stagger = opts.j != null ? ` style="--j:${opts.j}"` : "";
    return `<div class="${cls}" data-match="${m.id}"${stagger}>
      ${timeCell(m, opts)}
      <div class="match__teams">
        ${teamRow(m.home, "home", m)}
        ${teamRow(m.away, "away", m)}
      </div>
      ${scoreCell(m)}
      ${opts.mini ? "" : `<button class="match__fav${fav ? " is-on" : ""}" data-fav-match="${m.id}"
         aria-label="${esc(t("a11y.fav"))}">${starSvg(fav)}</button>`}
    </div>`;
  }

  function leagueBlock(group, idx) {
    const l = group.league;
    const name = Settings.get().lang === "tg" ? l.name_tg : l.name_ru;
    const country = Settings.get().lang === "tg" ? l.country_tg : l.country_ru;
    // У международных турниров (ЧМ, ЛЧ, Лига наций) флага страны нет —
    // подставляем эмблему турнира, она есть у всех лиг.
    const icon = l.flag || l.logo;
    const liveN = group.matches.filter(m => LIVE.has(m.status)).length;
    const badge = liveN
      ? `<span class="league-block__count league-block__count--live">${liveN} LIVE</span>`
      : `<span class="league-block__count">${group.matches.length}</span>`;
    // --i двигает каскад появления блоков (см. .league-block в CSS)
    return `<section class="card league-block" style="--i:${idx || 0}">
      <a class="league-block__head" href="/league/${l.id}">
        ${logo(icon, "league-block__flag", country)}
        <div class="league-block__text">
          <div class="league-block__country">${esc(country)}</div>
          <div class="league-block__name">${esc(name)}</div>
        </div>
        ${badge}
        <span class="league-block__arrow">›</span>
      </a>
      <div class="card__body">${group.matches.map((m, j) => matchRow(m, { j })).join("")}</div>
    </section>`;
  }

  function empty(titleKey, hintKey, icon) {
    return `<div class="empty">
      <div class="empty__icon">${icon || "⚽"}</div>
      <div class="empty__title">${esc(t(titleKey))}</div>
      ${hintKey ? `<div class="empty__hint">${esc(t(hintKey))}</div>` : ""}
    </div>`;
  }

  function skeleton(rows) {
    let out = "";
    for (let i = 0; i < (rows || 6); i++) {
      out += `<div class="sk-row">
        <div class="skeleton sk-line" style="width:34px"></div>
        <div><div class="skeleton sk-line" style="width:${45 + (i * 13) % 40}%;margin-bottom:7px"></div>
             <div class="skeleton sk-line" style="width:${38 + (i * 17) % 45}%"></div></div>
        <div class="skeleton sk-line" style="width:16px"></div>
      </div>`;
    }
    return `<div class="card">${out}</div>`;
  }

  /* Клики по матчу и звёздочкам — один обработчик на весь документ */
  document.addEventListener("click", e => {
    const favBtn = e.target.closest("[data-fav-match]");
    if (favBtn) {
      e.preventDefault(); e.stopPropagation();
      const on = Settings.toggleFavMatch(favBtn.dataset.favMatch);
      if (on === null) return;   // гость: Settings уже открыл окно входа
      favBtn.classList.toggle("is-on", on);
      favBtn.innerHTML = starSvg(on);
      if (window.App && App.renderFavorites) App.renderFavorites();
      return;
    }
    const row = e.target.closest("[data-match]");
    if (row && !e.target.closest("a")) location.href = "/match/" + row.dataset.match;
  });

  return { esc, logo, matchRow, leagueBlock, empty, skeleton, timeCell, scoreCell, LIVE, DONE, starSvg };
})();
