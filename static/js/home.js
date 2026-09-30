/* Главная: вкладки, лента матчей, автообновление live-счёта без перезагрузки. */
window.Home = (function () {
  const $ = s => document.querySelector(s);
  let tab = "date";          // live | all | date
  let curDate = null;        // ГГГГ-ММ-ДД, когда tab === "date"
  let feedTimer = null, liveTimer = null;
  let lastScores = {};

  const DAYS_BACK = 7, DAYS_FWD = 7;

  /* Сегодняшняя дата в часовом поясе пользователя, а не браузера:
     в настройках можно выбрать другой пояс, и лента должна следовать за ним. */
  function todayInTz() {
    const tz = Settings.get().tz;
    try {
      return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric",
        month: "2-digit", day: "2-digit" }).format(new Date());
    } catch (e) {
      return new Date().toISOString().slice(0, 10);
    }
  }

  function shiftDate(iso, days) {
    // полдень по UTC — чтобы переход на летнее время не сдвигал дату на сутки
    const d = new Date(iso + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }

  function labelFor(iso, offset) {
    if (offset === 0) return { main: t("tab.today"), sub: "" };
    if (offset === -1) return { main: t("tab.yesterday"), sub: "" };
    if (offset === 1) return { main: t("tab.tomorrow"), sub: "" };
    const d = new Date(iso + "T12:00:00Z");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const yy = String(d.getUTCFullYear()).slice(2);
    return { main: `${dd}.${mm}.${yy}`, sub: t("dow." + d.getUTCDay()) };
  }

  /* Лента дат: неделя назад, сегодня, неделя вперёд */
  function buildDayTabs() {
    const box = $("#tabsDays");
    if (!box) return;
    const today = todayInTz();
    let html = "";
    for (let i = -DAYS_BACK; i <= DAYS_FWD; i++) {
      const iso = shiftDate(today, i);
      const { main, sub } = labelFor(iso, i);
      const cls = "tab tab--day" + (i === 0 ? " tab--today" : "")
                + (tab === "date" && curDate === iso ? " is-active" : "");
      html += `<button class="${cls}" data-date="${iso}">
        <span class="tab__day">${UI.esc(main)}</span>
        ${sub ? `<span class="tab__dow">${UI.esc(sub)}</span>` : ""}
      </button>`;
    }
    box.innerHTML = html;
  }

  /* Активную вкладку подводим к центру, чтобы «сегодня» было видно сразу */
  function scrollToActive(smooth) {
    const bar = $("#tabs"), act = bar && bar.querySelector(".tab.is-active");
    if (!bar || !act) return;
    const left = act.offsetLeft - bar.clientWidth / 2 + act.offsetWidth / 2;
    bar.scrollTo({ left: Math.max(0, left), behavior: smooth ? "smooth" : "auto" });
  }

  async function load() {
    const box = $("#feed");
    box.innerHTML = UI.skeleton(7);
    try {
      const data = await API.matches(tab, tab === "date" ? curDate : null);
      render(data);
    } catch (e) {
      box.innerHTML = UI.empty("empty.matches", "empty.matches.hint", "⚠️");
    }
  }

  function render(data) {
    const box = $("#feed");

    // Вкладка LIVE показывает только идущие матчи. Бэкенд их уже отфильтровал,
    // но матч мог закончиться между запросом и отрисовкой — подстраховываемся здесь,
    // иначе в «живых» повисали бы завершённые игры.
    let groups = data.groups;
    if (tab === "live") {
      groups = groups
        .map(g => ({ ...g, matches: g.matches.filter(m => UI.LIVE.has(m.status)) }))
        .filter(g => g.matches.length);
    }

    if (!groups.length) {
      box.innerHTML = tab === "live"
        ? UI.empty("empty.live", "empty.live.hint", "⏱")
        : UI.empty("empty.matches", "empty.matches.hint", "📅");
    } else {
      // избранные лиги — наверх
      const favs = Settings.get().favLeagues;
      groups = [...groups].sort((a, b) => {
        const fa = favs.includes(a.league.id) ? 0 : 1, fb = favs.includes(b.league.id) ? 0 : 1;
        return fa - fb || a.league.priority - b.league.priority;
      });
      box.innerHTML = groups.map(UI.leagueBlock).join("");
    }
    // короткое затухание, чтобы подмена содержимого не «прыгала»
    box.classList.remove("feed-swap");
    void box.offsetWidth;
    box.classList.add("feed-swap");
    lastScores = {};
    data.groups.forEach(g => g.matches.forEach(m => {
      lastScores[m.id] = (m.goals.home ?? "") + ":" + (m.goals.away ?? "");
    }));
    updateLiveCount(data.live_count);
  }

  function updateLiveCount(n) {
    const el = $("#cntLive");
    if (el) el.textContent = n ?? 0;
  }

  /* Точечное обновление счёта и минуты — без перерисовки всей ленты */
  async function pollLive() {
    try {
      const { matches } = await API.liveScores();
      updateLiveCount(matches.length);

      matches.forEach(m => {
        const row = document.querySelector(`.match[data-match="${m.id}"]`);
        if (!row) return;
        row.classList.add("is-live");

        // минута
        const timeCell = row.querySelector(".match__time");
        if (timeCell) {
          const min = m.elapsed != null ? m.elapsed + (m.extra_minute ? "+" + m.extra_minute : "") : "";
          timeCell.className = "match__time match__time--live";
          timeCell.innerHTML = m.status === "HT"
            ? `<span class="match__pulse"></span>${t("status.short.ht")}`
            : `<span class="match__pulse"></span>${min}`;
        }

        // счёт
        const key = (m.home ?? "") + ":" + (m.away ?? "");
        let score = row.querySelector("[data-score]");
        if (!score) return;
        score.className = "match__score match__score--live";
        const cells = score.querySelectorAll("div");
        if (cells.length === 2) {
          const changed = lastScores[m.id] !== undefined && lastScores[m.id] !== key;
          cells[0].textContent = m.home ?? 0;
          cells[1].textContent = m.away ?? 0;
          if (changed) {
            score.classList.add("score-flash");
            setTimeout(() => score.classList.remove("score-flash"), 950);
          }
        }
        lastScores[m.id] = key;
      });

      // матч закончился и пропал из живых — перезагружаем ленту
      const liveIds = new Set(matches.map(m => m.id));
      const stale = [...document.querySelectorAll(".match.is-live")]
        .filter(el => !liveIds.has(Number(el.dataset.match)));
      if (stale.length) load();
    } catch (e) { /* сеть моргнула — попробуем на следующем тике */ }
  }

  function setTab(name, date) {
    tab = name;
    if (name === "date") curDate = date;
    document.querySelectorAll("#tabs .tab").forEach(b => {
      const on = name === "date" ? b.dataset.date === date : b.dataset.tab === name;
      b.classList.toggle("is-active", on);
    });
    scrollToActive(true);
    load();
  }

  function init() {
    curDate = todayInTz();
    buildDayTabs();
    scrollToActive(false);

    $("#tabs")?.addEventListener("click", e => {
      const b = e.target.closest(".tab");
      if (!b) return;
      if (b.dataset.date) setTab("date", b.dataset.date);
      else if (b.dataset.tab) setTab(b.dataset.tab);
    });
    load();
    // На LIVE новый начавшийся матч должен появляться быстро, на остальных вкладках
    // перерисовывать ленту часто незачем — данные меняются редко.
    feedTimer = setInterval(() => {
      if (document.hidden) return;
      load();
    }, 120000);
    liveTimer = setInterval(() => {
      if (document.hidden) return;
      if (tab === "live") load(); else pollLive();
    }, 20000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) pollLive(); });
    document.addEventListener("tajscore:settings", () => {
      curDate = curDate || todayInTz();
      buildDayTabs();
      load();
    });
  }

  return { init, setTab, load };
})();
