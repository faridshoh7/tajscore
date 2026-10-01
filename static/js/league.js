/* Страница лиги: таблица, календарь, результаты, статистика игроков, плей-офф. */
window.LeaguePage = (function () {
  const esc = UI.esc;
  let id = null, data = null, sub = "table", cat = "goals";

  const CATS = [["goals", "league.scorers"], ["assists", "league.assists"],
                ["yellow", "league.yellow"], ["red", "league.red"]];

  /* Какие вкладки показывать — зависит от того, что реально есть у лиги */
  function tabsFor(d) {
    const out = [];
    if (d.standings && d.standings.length) out.push(["table", "league.table"]);
    if (d.bracket && d.bracket.length) out.push(["bracket", "league.bracket"]);
    out.push(["fixtures", "league.fixtures"], ["results", "league.results"],
             ["players", "league.players"]);
    return out;
  }

  const DARK_LOGO_IDS = [1, 2, 3, 5, 848];
  function hero(l) {
    const lang = Settings.get().lang;
    const name = pick(l, "name");
    const country = pick(l, "country");
    const dark = DARK_LOGO_IDS.includes(l.id) ? " lhero--dark-logo" : "";
    return `<div class="card lhero${dark}">
      ${UI.logo(l.logo, "lhero__logo", name)}
      <div class="lhero__text">
        <h1 class="lhero__name">${esc(name)}</h1>
        <div class="lhero__meta">
          ${l.flag ? `<img src="${esc(l.flag)}" alt="">` : ""}
          <span>${esc(country)}</span>
          <span class="lhero__dot">•</span>
          <span>${esc(t("league.season"))} ${esc(l.season)}</span>
        </div>
      </div>
    </div>`;
  }

  /* ---------------------------------------------------------------- таблица */
  function table(groups) {
    if (!groups.length) return UI.empty("empty.table", "empty.table.hint", "📊");
    return groups.map(g => `
      <section class="card league-sec">
        ${g.group ? `<div class="card__head"><span class="card__title">${esc(g.group)}</span></div>` : ""}
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr>
              <th class="c-rank">#</th>
              <th class="l">${esc(t("tbl.team"))}</th>
              <th>${esc(t("tbl.played"))}</th>
              <th class="hide-sm">${esc(t("tbl.win"))}</th>
              <th class="hide-sm">${esc(t("tbl.draw"))}</th>
              <th class="hide-sm">${esc(t("tbl.lose"))}</th>
              <th class="hide-sm">${esc(t("tbl.goals"))}</th>
              <th>${esc(t("tbl.gd"))}</th>
              <th class="c-pts">${esc(t("tbl.points"))}</th>
              <th class="hide-sm">${esc(t("tbl.form"))}</th>
            </tr></thead>
            <tbody>${g.rows.map(r => `
              <tr class="${r.zone ? "zone-" + r.zone : ""}" data-team="${r.team_id}">
                <td class="c-rank">${r.rank}</td>
                <td class="c-team"><div>
                  ${UI.logo(r.logo, "", tname(r, "team", "team_tg", "team_en"))}<span>${esc(tname(r, "team", "team_tg", "team_en"))}</span>
                </div></td>
                <td>${r.played}</td>
                <td class="hide-sm">${r.win}</td>
                <td class="hide-sm">${r.draw}</td>
                <td class="hide-sm">${r.lose}</td>
                <td class="hide-sm">${r.gf}:${r.ga}</td>
                <td>${r.gd > 0 ? "+" + r.gd : r.gd}</td>
                <td class="c-pts">${r.points}</td>
                <td class="hide-sm"><div class="form-row">${(r.form || []).slice(-5)
                  .map(f => `<span class="form-badge form-badge--${esc(f)}">${esc(tform(f))}</span>`).join("")}</div></td>
              </tr>`).join("")}
            </tbody>
          </table>
        </div>
        ${zoneLegend(g.rows)}
      </section>`).join("");
  }

  /* Подпись к цветным полоскам — иначе они ничего не значат для читателя */
  function zoneLegend(rows) {
    const seen = [...new Set(rows.map(r => r.zone).filter(Boolean))];
    if (!seen.length) return "";
    return `<div class="zone-legend">${seen.map(z =>
      `<span class="zone-legend__item"><i class="zone-dot zone-dot--${esc(z)}"></i>${esc(t("zone." + z))}</span>`
    ).join("")}</div>`;
  }

  /* ---------------------------------------------------------------- матчи */
  function matchList(list, emptyKey) {
    if (!list.length) return UI.empty(emptyKey, null, "📅");
    // группируем по дате — так же, как это делает Flashscore
    const byDay = {};
    list.forEach(m => {
      const d = Settings.formatDate ? Settings.formatDate(m.timestamp) : m.date_utc.slice(0, 10);
      (byDay[d] = byDay[d] || []).push(m);
    });
    return Object.entries(byDay).map(([day, ms], i) => `
      <section class="card league-sec" style="--i:${i}">
        <div class="card__head"><span class="card__title">${esc(day)}</span>
          <span class="league-block__count">${ms.length}</span></div>
        <div class="card__body">${ms.map((m, j) => UI.matchRow(m, { j })).join("")}</div>
      </section>`).join("");
  }

  /* ---------------------------------------------------------------- игроки */
  function playersBlock(all) {
    const list = all[cat] || [];
    const seg = `<div class="seg seg--yellow league-catseg" id="catSeg">${CATS.map(([k, i]) =>
      `<button data-cat="${k}" class="${cat === k ? "is-active" : ""}">${esc(t(i))}</button>`).join("")}</div>`;
    if (!list.length) return seg + UI.empty("empty.players", "empty.players.hint", "👤");
    return seg + `<section class="card league-sec">
      <div class="card__body">${list.map((p, i) => `
        <div class="prow" data-team="${p.team_id}" style="--j:${i}">
          <div class="prow__rank">${p.rank}</div>
          ${photoCell(p)}
          <div class="prow__info">
            <div class="prow__name">${esc(tname(p))}</div>
            <div class="prow__team">${UI.logo(p.team_logo, "", tname(p, "team_name", "team_name_tg", "team_name_en"))}<span>${esc(tname(p, "team_name", "team_name_tg", "team_name_en"))}</span></div>
          </div>
          <div class="prow__val">${p.value}</div>
        </div>`).join("")}
      </div>
    </section>`;
  }


  /* Портрет игрока: жёсткие 3:4, чтобы строки не прыгали. Фото есть не у всех —
     вместо него заглушка с первой буквой фамилии, а не пустая дыра. */
  function photoCell(p) {
    if (p.photo) {
      return `<img class="prow__photo" src="${esc(p.photo)}" alt="" loading="lazy"
                   onerror="this.replaceWith(Object.assign(document.createElement('div'),
                            {className:'prow__photo prow__photo--none'}))">`;
    }
    const nm = tname(p) || "";
    const letter = (nm.split(" ").slice(-1)[0] || nm).slice(0, 1).toUpperCase();
    return `<div class="prow__photo prow__photo--none">${esc(letter)}</div>`;
  }

  /* ---------------------------------------------------------------- плей-офф */
  function bracket(stages) {
    if (!stages.length) return UI.empty("empty.matches", null, "🏆");
    return `<div class="card"><div class="bracket">${stages.map(s => `
      <div class="bracket__stage">
        <div class="bracket__title">${esc(s.stage)}</div>
        ${s.matches.map(m => `
          <div class="bracket__match" data-match="${m.id}">
            ${["home", "away"].map(side => {
              const tm = m[side], win = m.winner === side, lose = m.winner && m.winner !== side;
              const nm = tname(tm);
              return `<div class="bracket__team${win ? " bracket__team--win" : lose ? " bracket__team--lose" : ""}">
                ${UI.logo(tm.logo, "", nm)}<span>${esc(nm)}</span><b>${m.goals[side] ?? "–"}</b>
              </div>`;
            }).join("")}
          </div>`).join("")}
      </div>`).join("")}</div></div>`;
  }

  /* ---------------------------------------------------------------- сборка */
  function body() {
    if (sub === "table") return table(data.standings);
    if (sub === "bracket") return bracket(data.bracket);
    if (sub === "fixtures") return matchList(data.upcoming, "empty.fixtures");
    if (sub === "results") return matchList(data.results, "empty.results");
    if (sub === "players") return playersBlock(data.players);
    return "";
  }

  function render() {
    const tabs = tabsFor(data);
    if (!tabs.some(([k]) => k === sub)) sub = tabs[0][0];
    document.querySelector("#leaguePage").innerHTML = `
      ${hero(data.league)}
      <div class="subtabs" id="lsubtabs">${tabs.map(([k, i]) =>
        `<button class="subtab${sub === k ? " is-active" : ""}" data-sub="${k}">${esc(t(i))}</button>`).join("")}</div>
      <div id="lbody" class="feed-swap">${body()}</div>`;
  }

  function swap() {
    const box = document.querySelector("#lbody");
    box.innerHTML = body();
    box.classList.remove("feed-swap");
    void box.offsetWidth;
    box.classList.add("feed-swap");
  }

  async function init(leagueId) {
    id = leagueId;
    const page = document.querySelector("#leaguePage");
    page.innerHTML = UI.skeleton(8);
    try {
      data = await API.league(id);
    } catch (e) {
      page.innerHTML = UI.empty("empty.matches", "empty.matches.hint", "⚠️");
      return;
    }
    const lang = Settings.get().lang;
    document.title = pick(data.league, "name") + " — Tajscore";
    render();

    page.addEventListener("click", e => {
      const tab = e.target.closest("[data-sub]");
      if (tab) {
        sub = tab.dataset.sub;
        document.querySelectorAll("#lsubtabs .subtab")
          .forEach(x => x.classList.toggle("is-active", x === tab));
        swap();
        return;
      }
      const c = e.target.closest("[data-cat]");
      if (c) {
        cat = c.dataset.cat;
        swap();
        return;
      }
      // строка таблицы или игрока ведёт на команду
      const row = e.target.closest("[data-team]");
      if (row && row.dataset.team) location.href = "/team/" + row.dataset.team;
    });

    document.addEventListener("tajscore:settings", () => { render(); });
  }

  return { init };
})();
