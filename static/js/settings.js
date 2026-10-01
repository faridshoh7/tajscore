/* Настройки пользователя в localStorage: тема, язык, часовой пояс, формат времени, избранное. */
(function () {
  const KEY = "tajscore.settings";
  const DEFAULTS = {
    theme: "dark",
    lang: "ru",
    tz: "Asia/Dushanbe",
    timeFormat: "24",
    favLeagues: [],
    favMatches: [],
    favTeams: []
  };

  /* Город берётся из словаря по ключу tz.<зона> (см. i18n.js), здесь только
     смещение — оно от языка не зависит. */
  const TIMEZONES = [
    ["Asia/Dushanbe", "UTC+5"],
    ["Asia/Tashkent", "UTC+5"],
    ["Asia/Almaty", "UTC+6"],
    ["Europe/Moscow", "UTC+3"],
    ["Europe/Kyiv", "UTC+3"],
    ["Europe/Berlin", "UTC+1/+2"],
    ["Europe/London", "UTC+0/+1"],
    ["Asia/Dubai", "UTC+4"],
    ["Asia/Istanbul", "UTC+3"],
    ["America/New_York", "UTC-5/-4"],
    ["UTC", ""]
  ];

  let state = Object.assign({}, DEFAULTS);
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
    state = Object.assign(state, saved);
  } catch (e) { /* повреждённые настройки — просто берём значения по умолчанию */ }

  const listeners = [];

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
    apply();
    listeners.forEach(fn => fn(state));
  }

  function apply() {
    document.documentElement.dataset.theme = state.theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = state.theme === "dark" ? "#060A12" : "#EFF2F8";
    if (window.applyI18n) applyI18n();
  }

  window.Settings = {
    TIMEZONES,
    get: () => state,
    set(patch) { Object.assign(state, patch); save(); },
    onChange(fn) { listeners.push(fn); },

    /* Избранное — только для авторизованных. Гостю показываем окно входа и
       возвращаем null: по нему вызывающий код понимает, что ничего не изменилось.
       Локальные массивы теперь зеркало серверных — рисуем из них синхронно,
       а сама правка уходит на сервер в фоне. */
    toggleFav(kind, id) {
      if (!window.Auth || !Auth.user()) { if (window.Auth) Auth.promptLogin(); return null; }
      id = Number(id);
      const list = kind === "league" ? state.favLeagues
                 : kind === "team"   ? (state.favTeams = state.favTeams || [])
                 : state.favMatches;
      const i = list.indexOf(id);
      if (i >= 0) list.splice(i, 1); else list.push(id);
      save();
      const on = list.includes(id);
      Auth.pushFavorite(kind, id, on);
      return on;
    },
    toggleFavLeague(id) { return this.toggleFav("league", id); },
    toggleFavMatch(id)  { return this.toggleFav("match", id); },
    toggleFavTeam(id)   { return this.toggleFav("team", id); },
    isFavLeague: id => state.favLeagues.includes(Number(id)),
    isFavMatch:  id => state.favMatches.includes(Number(id)),
    isFavTeam:   id => (state.favTeams || []).includes(Number(id)),

    /* Заливает избранное, пришедшее с сервера: вход, выход, синхронизация. */
    setFavorites(fav) {
      state.favLeagues = (fav.league || []).map(Number);
      state.favMatches = (fav.match  || []).map(Number);
      state.favTeams   = (fav.team   || []).map(Number);
      save();
    },

    /* Время матча в часовом поясе пользователя */
    formatTime(ts) {
      const opts = {
        hour: "2-digit", minute: "2-digit",
        hour12: state.timeFormat === "12",
        timeZone: state.tz
      };
      try { return new Intl.DateTimeFormat("ru-RU", opts).format(new Date(ts * 1000)); }
      catch (e) { return new Date(ts * 1000).toISOString().slice(11, 16); }
    },
    /* Матч идёт сегодня — по календарю часового пояса пользователя */
    isToday(ts) {
      try {
        const f = new Intl.DateTimeFormat("en-CA", { timeZone: state.tz, year: "numeric",
          month: "2-digit", day: "2-digit" });
        return f.format(new Date(ts * 1000)) === f.format(new Date());
      } catch (e) { return true; }
    },
    /* Короткая дата ДД.ММ в часовом поясе пользователя */
    formatDayMonth(ts) {
      try {
        return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit",
          timeZone: state.tz }).format(new Date(ts * 1000));
      } catch (e) { return ""; }
    },
    formatDate(ts, withYear) {
      const opts = { day: "2-digit", month: "short", timeZone: state.tz };
      if (withYear) opts.year = "numeric";
      try { return new Intl.DateTimeFormat("ru-RU", opts).format(new Date(ts * 1000)); }
      catch (e) { return ""; }
    }
  };

  apply();
})();
