/* Страница команды: эмблема, краткая справка и последние матчи. */
window.TeamPage = (function () {
  const esc = UI.esc;

  function hero(tm) {
    const name = tname(tm);
    // Город клубы Лигаи Олӣ отдают отдельно (см. app/teams_tj.py); у остальных
    // в этой строке остаётся страна из API.
    const city = tname(tm, "city_ru", "city_tg");
    const bits = [city || tm.country, tm.founded ? t("team.founded") + " " + tm.founded : null]
      .filter(Boolean);
    const fav = Settings.isFavTeam(tm.id);
    return `<div class="card lhero">
      ${UI.logo(tm.logo, "lhero__logo", name)}
      <div class="lhero__text">
        <h1 class="lhero__name">${esc(name)}</h1>
        <div class="lhero__meta">${bits.map(b => `<span>${esc(b)}</span>`)
          .join('<span class="lhero__dot">•</span>')}</div>
      </div>
      <button class="lhero__fav${fav ? " is-on" : ""}" data-fav-team="${tm.id}"
              aria-label="${esc(t("a11y.fav"))}">${UI.starSvg(fav)}</button>
    </div>`;
  }

  /* Звёздочка команды: гостю Settings сам покажет окно входа и вернёт null */
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-fav-team]");
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    const on = Settings.toggleFavTeam(b.dataset.favTeam);
    if (on === null) return;
    b.classList.toggle("is-on", on);
    b.innerHTML = UI.starSvg(on);
  });

  async function init(teamId) {
    const page = document.querySelector("#teamPage");
    page.innerHTML = UI.skeleton(6);
    let d;
    try {
      d = await API.team(teamId);
    } catch (e) {
      page.innerHTML = UI.empty("empty.matches", "empty.matches.hint", "⚠️");
      return;
    }
    document.title = tname(d.team) + " — Tajscore";
    const list = d.matches.length
      ? `<section class="card league-sec">
           <div class="card__head"><span class="card__title">${esc(t("team.matches"))}</span>
             <span class="league-block__count">${d.matches.length}</span></div>
           <div class="card__body">${d.matches.map((m, j) => UI.matchRow(m, { j })).join("")}</div>
         </section>`
      : UI.empty("empty.matches", null, "📅");
    page.innerHTML = hero(d.team) + list;
  }

  return { init };
})();
