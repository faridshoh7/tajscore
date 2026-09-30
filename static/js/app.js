/* Общий каркас: сайдбар лиг, поиск, настройки, правая колонка, мобильная навигация. */
window.App = (function () {
  const $ = s => document.querySelector(s);
  const esc = UI.esc;
  let leaguesCache = [];

  /* ------------------------------------------------------------- левая колонка */
  async function renderLeagues(activeId) {
    const box = $("#leaguesList");
    if (!box) return;
    try {
      const data = await API.leagues();
      leaguesCache = data.leagues;
    } catch (e) { box.innerHTML = UI.empty("empty.matches"); return; }

    const favs = Settings.get().favLeagues;
    const sorted = [...leaguesCache].sort((a, b) => {
      const fa = favs.includes(a.id) ? 0 : 1, fb = favs.includes(b.id) ? 0 : 1;
      return fa - fb || a.priority - b.priority;
    });
    const lang = Settings.get().lang;
    box.innerHTML = sorted.map(l => {
      const name = lang === "tg" ? l.name_tg : l.name_ru;
      const country = lang === "tg" ? l.country_tg : l.country_ru;
      const isFav = favs.includes(l.id);
      const badge = l.live_count
        ? `<span class="league-item__badge league-item__badge--live">${l.live_count}</span>`
        : (l.today_count ? `<span class="league-item__badge">${l.today_count}</span>` : "");
      return `<a class="league-item${activeId === l.id ? " is-active" : ""}" href="/league/${l.id}">
        ${UI.logo(l.flag || l.logo, "league-item__flag", country)}
        <div class="league-item__text">
          <div class="league-item__name">${esc(name)}</div>
          <div class="league-item__country">${esc(country)}</div>
        </div>
        ${badge}
        <button class="league-item__star${isFav ? " is-on" : ""}" data-fav-league="${l.id}"
                aria-label="${esc(t("a11y.fav"))}">${UI.starSvg(isFav)}</button>
      </a>`;
    }).join("");
    renderFavLeagueList();
  }

  document.addEventListener("click", e => {
    const b = e.target.closest("[data-fav-league]");
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    if (Settings.toggleFavLeague(b.dataset.favLeague) === null) return;
    renderLeagues(window.__activeLeagueId);
  });

  /* ------------------------------------------------------------- правая колонка */
  async function renderPopular() {
    const box = $("#popularList");
    if (!box) return;
    try {
      const { matches } = await API.popular();
      box.innerHTML = matches.length
        ? matches.map(m => UI.matchRow(m, { mini: true, showDate: true })).join("")
        : UI.empty("empty.live", null, "🕐");
    } catch (e) { box.innerHTML = ""; }
  }

  async function renderFavorites() {
    const box = $("#favoritesList");
    if (!box) return;
    if (window.Auth && !Auth.user()) {
      box.innerHTML = UI.empty("empty.favorites.guest", "empty.favorites.guest.hint", "🔒");
      return;
    }
    const ids = Settings.get().favMatches;
    if (!ids.length) { box.innerHTML = UI.empty("empty.favorites", "empty.favorites.hint", "⭐"); return; }
    try {
      const list = await Promise.all(ids.slice(-8).map(id => API.match(id).catch(() => null)));
      const ok = list.filter(Boolean);
      box.innerHTML = ok.length
        ? ok.map(m => UI.matchRow(m, { mini: true })).join("")
        : UI.empty("empty.favorites", "empty.favorites.hint", "⭐");
    } catch (e) { box.innerHTML = ""; }
  }

  /* ------------------------------------------------------------- поиск */
  function initSearch() {
    const input = $("#searchInput"), box = $("#searchResults");
    if (!input) return;
    let timer = null;

    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) { box.classList.remove("is-open"); return; }
      timer = setTimeout(async () => {
        try {
          const r = await API.search(q);
          const lang = Settings.get().lang;
          let html = "";
          if (r.leagues.length) html += `<div class="search__group">
            <div class="search__label">${esc(t("search.leagues"))}</div>` +
            r.leagues.map(l => `<a class="search__item" href="/league/${l.id}">
              ${UI.logo(l.logo, "", "")}<span>${esc(lang === "tg" ? l.name_tg : l.name_ru)}</span>
              <small>${esc(lang === "tg" ? l.country_tg : l.country_ru)}</small></a>`).join("") + `</div>`;
          if (r.teams.length) html += `<div class="search__group">
            <div class="search__label">${esc(t("search.teams"))}</div>` +
            r.teams.map(x => `<a class="search__item" href="/team/${x.id}">
              ${UI.logo(x.logo, "", tname(x))}<span>${esc(tname(x))}</span></a>`).join("") + `</div>`;
          if (r.matches.length) html += `<div class="search__group">
            <div class="search__label">${esc(t("search.matches"))}</div>` +
            r.matches.map(m => `<a class="search__item" href="/match/${m.id}">
              <span>${esc(tname(m.home))} — ${esc(tname(m.away))}</span>
              <small>${esc(Settings.formatDate(m.timestamp))}</small></a>`).join("") + `</div>`;
          box.innerHTML = html || `<div class="empty" style="padding:22px">${esc(t("search.empty"))}</div>`;
          box.classList.add("is-open");
        } catch (e) { box.classList.remove("is-open"); }
      }, 220);
    });

    document.addEventListener("click", e => {
      if (!e.target.closest("#search")) box.classList.remove("is-open");
    });
    input.addEventListener("keydown", e => { if (e.key === "Escape") box.classList.remove("is-open"); });
  }

  /* ------------------------------------------------------------- настройки */
  let openSettings = () => {};

  function initSettings() {
    const drawer = $("#drawer"), overlay = $("#overlay");
    const open = () => { drawer.classList.add("is-open"); overlay.classList.add("is-open");
                         drawer.setAttribute("aria-hidden", "false"); loadStatus(); };
    openSettings = open;
    const close = () => { drawer.classList.remove("is-open"); overlay.classList.remove("is-open");
                          drawer.setAttribute("aria-hidden", "true"); };
    $("#btnSettings")?.addEventListener("click", open);
    $("#btnCloseSettings")?.addEventListener("click", close);
    overlay?.addEventListener("click", close);
    document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });

    // сегменты: тема / язык / формат времени
    const segs = [["#segTheme", "theme"], ["#segLang", "lang"], ["#segTimeFmt", "timeFormat"]];
    segs.forEach(([sel, key]) => {
      const el = $(sel); if (!el) return;
      const sync = () => el.querySelectorAll("button").forEach(b =>
        b.classList.toggle("is-active", b.dataset.val === String(Settings.get()[key])));
      el.addEventListener("click", e => {
        const b = e.target.closest("button"); if (!b) return;
        Settings.set({ [key]: b.dataset.val });
        sync();
        document.dispatchEvent(new CustomEvent("tajscore:settings"));
      });
      sync();
    });

    // часовой пояс
    const sel = $("#selTz");
    if (sel) {
      renderTz();
      sel.addEventListener("change", () => {
        Settings.set({ tz: sel.value });
        document.dispatchEvent(new CustomEvent("tajscore:settings"));
      });
    }
  }

  /* Названия городов в списке поясов зависят от языка, поэтому список
     пересобирается при каждом переключении. */
  function renderTz() {
    const sel = $("#selTz");
    if (!sel) return;
    sel.innerHTML = Settings.TIMEZONES.map(([v, offset]) =>
      `<option value="${v}">${esc(t("tz." + v, v))}${offset ? " (" + esc(offset) + ")" : ""}</option>`).join("");
    sel.value = Settings.get().tz;
  }

  function renderFavLeagueList() {
    const box = $("#favLeagues");
    if (!box || !leaguesCache.length) return;
    const lang = Settings.get().lang;
    box.innerHTML = leaguesCache.map(l => {
      const on = Settings.isFavLeague(l.id);
      return `<div class="fav-row" data-fav-league="${l.id}">
        ${UI.logo(l.logo, "", "")}
        <span>${esc(lang === "tg" ? l.name_tg : l.name_ru)}</span>
        <span class="fav-row__star${on ? " is-on" : ""}">${UI.starSvg(on)}</span>
      </div>`;
    }).join("");
  }

  async function loadStatus() {
    try {
      const s = await API.status();
      const b = s.budget;
      $("#statusLine").innerHTML =
        `${esc(t("status.fixtures"))}: <b class="mono">${s.db.fixtures}</b><br>` +
        `${esc(t("status.teams"))}: <b class="mono">${s.db.teams}</b><br>` +
        `${esc(t("status.requests"))}: <b class="mono">${b.used}/${b.hard_limit}</b><br>` +
        `${esc(t("status.sync"))}: <b>${esc(t(s.worker.running ? "status.sync.on" : "status.sync.off"))}</b>` +
        (s.worker.live_mode ? ` · ${esc(t("status.livemode"))}` : "");
    } catch (e) { $("#statusLine").textContent = "—"; }
  }

  /* ------------------------------------------------------------- мобильная навигация */
  function initMobile() {
    const left = $("#colLeft");
    $("#btnLeagues")?.addEventListener("click", () => {
      left.classList.toggle("is-open");
      $("#btnLeagues").classList.toggle("is-active", left.classList.contains("is-open"));
    });
    $("#mobnav")?.addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b) return;
      $("#mobnav").querySelectorAll("button").forEach(x => x.classList.toggle("is-active", x === b));
      const nav = b.dataset.nav;
      left.classList.toggle("is-open", nav === "leagues");
      if (nav === "live" && window.Home) Home.setTab("live");
      if (nav === "matches" && window.Home) Home.setTab("today");
      if (nav === "favorites") {
        if (location.pathname !== "/") { location.href = "/"; return; }
        document.querySelector("#colRight")?.scrollIntoView({ behavior: "smooth" });
      }
    });
  }

  /* Кнопка «назад»: если пользователь пришёл на страницу извне (по ссылке из
     мессенджера), истории нет — возвращаем на главную, а не в пустоту. */
  function initBack() {
    const b = document.getElementById("btnBack");
    if (!b) return;
    b.addEventListener("click", () => {
      if (history.length > 1 && document.referrer.includes(location.host)) history.back();
      else location.href = "/";
    });
  }

  function init(opts) {
    initBack();
    opts = opts || {};
    window.__activeLeagueId = opts.activeLeagueId;
    applyI18n();
    initSearch();
    initSettings();
    initMobile();
    renderLeagues(opts.activeLeagueId);
    renderPopular();
    renderFavorites();
    setInterval(renderPopular, 60000);

    /* Вход/выход меняет и звёздочки, и правую колонку — перерисовываем всё,
       что зависит от избранного. */
    if (window.Auth) {
      Auth.onChange(() => {
        renderLeagues(window.__activeLeagueId);
        renderFavorites();
      });
      Auth.init();
    }
    document.addEventListener("tajscore:settings", () => {
      applyI18n();
      renderTz();
      loadStatus();
      renderLeagues(window.__activeLeagueId);
      renderPopular();
      renderFavorites();
    });
  }

  return { init, renderLeagues, renderPopular, renderFavorites,
           openSettings: () => openSettings(), leagues: () => leaguesCache };
})();
