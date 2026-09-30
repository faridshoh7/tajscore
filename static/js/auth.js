/* Вход через Telegram, профиль и серверное избранное.

   Сессия лежит в httpOnly-cookie — отсюда она не видна и не нужна:
   браузер сам подставляет её в каждый fetch. */
window.Auth = (function () {
  const $ = s => document.querySelector(s);
  let user = null;
  let poller = null;
  const listeners = [];

  async function req(path, opts) {
    const r = await fetch(path, Object.assign({
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      credentials: "same-origin"
    }, opts || {}));
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }
  const post = (path, body) =>
    req(path, { method: "POST", body: JSON.stringify(body || {}) });

  function emit() {
    renderHeader();
    renderProfile();
    listeners.forEach(fn => fn(user));
  }

  /* ------------------------------------------------------------- шапка */
  function renderHeader() {
    const btn = $("#btnAuth");
    if (!btn) return;
    if (user) {
      btn.classList.add("auth-btn--user");
      btn.textContent = user.name;
      btn.title = t("auth.profile");
    } else {
      btn.classList.remove("auth-btn--user");
      btn.textContent = t("auth.login.short");
      btn.title = t("auth.login");
    }
  }

  /* ------------------------------------------------------------- профиль в настройках */
  function renderProfile() {
    const box = $("#profileSection");
    if (!box) return;
    if (!user) {
      box.innerHTML = `
        <div class="drawer__label">${t("auth.profile")}</div>
        <div class="profile-guest">
          <div class="profile-guest__text">${t("auth.guest.hint")}</div>
          <button class="btn-tg" id="profileLogin">${t("auth.login.tg")}</button>
        </div>`;
      return;
    }
    const on = user.notifications ? " is-on" : "";
    box.innerHTML = `
      <div class="drawer__label">${t("auth.profile")}</div>
      <div class="profile">
        <div class="profile__ava">${UI.esc(user.name.slice(0, 1).toUpperCase())}</div>
        <div class="profile__text">
          <div class="profile__name">${UI.esc(user.name)}</div>
          <div class="profile__uname">${user.username ? "@" + UI.esc(user.username) : ""}</div>
        </div>
      </div>
      <label class="switch-row">
        <span>${t("auth.notify")}</span>
        <span class="switch${on}" id="swNotify" role="switch"
              aria-checked="${user.notifications}" tabindex="0"></span>
      </label>
      <button class="btn-logout" id="btnLogout">${t("auth.logout")}</button>`;
  }

  /* ------------------------------------------------------------- модалка входа */
  function openModal(html) {
    const m = $("#authModal");
    if (!m) return;
    $("#authModalBody").innerHTML = html;
    m.classList.add("is-open");
    m.setAttribute("aria-hidden", "false");
  }

  function closeModal() {
    const m = $("#authModal");
    if (!m) return;
    m.classList.remove("is-open");
    m.setAttribute("aria-hidden", "true");
    stopPoll();
  }

  function stopPoll() {
    if (poller) { clearInterval(poller); poller = null; }
  }

  /* Гость тронул звёздочку — объясняем, зачем вход */
  function promptLogin() {
    openModal(`
      <div class="authbox">
        <div class="authbox__icon">⭐</div>
        <div class="authbox__title">${t("auth.need.title")}</div>
        <div class="authbox__text">${t("auth.need.text")}</div>
        <button class="btn-tg" id="authGo">${t("auth.login.tg")}</button>
      </div>`);
  }

  async function login() {
    /* Вкладку открываем СИНХРОННО, до единого await: после него браузер уже
       не считает открытие «действием пользователя» и блокирует popup.
       Адрес подставим, когда сервер вернёт токен. */
    const tab = window.open("", "_blank");

    let data;
    try {
      data = await post("/api/auth/start");
    } catch (e) {
      if (tab) tab.close();
      openModal(`<div class="authbox"><div class="authbox__title">${t("auth.error")}</div></div>`);
      return;
    }
    if (data.already) {
      if (tab) tab.close();
      user = data.user; emit(); closeModal(); return;
    }

    if (tab) tab.location = data.url;
    else window.open(data.url, "_blank", "noopener");   // вкладку заблокировали — пробуем ещё раз

    openModal(`
      <div class="authbox">
        <div class="authbox__spinner"></div>
        <div class="authbox__title">${t("auth.wait.title")}</div>
        <div class="authbox__text">${t("auth.wait.text")}</div>
        <a class="btn-tg" href="${data.url}" target="_blank" rel="noopener">${t("auth.open.bot")}</a>
        <div class="authbox__timer" id="authTimer"></div>
      </div>`);

    let left = data.expires_in || 300;
    const timer = $("#authTimer");
    stopPoll();
    poller = setInterval(async () => {
      left -= 2;
      if (timer) timer.textContent = left > 0
        ? t("auth.wait.timer") + " " + Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0")
        : "";
      if (left <= 0) { stopPoll(); expired(); return; }
      let res;
      try { res = await req("/api/auth/poll?token=" + encodeURIComponent(data.token)); }
      catch (e) { return; }   // сеть моргнула — попробуем на следующем тике
      if (res.status === "ok") {
        stopPoll();
        user = res.user;
        await syncFavorites(true);
        emit();
        openModal(`<div class="authbox">
            <div class="authbox__icon">✅</div>
            <div class="authbox__title">${t("auth.done")}</div>
            <div class="authbox__text">${UI.esc(user.name)}</div>
          </div>`);
        setTimeout(closeModal, 1500);
      } else if (res.status === "expired" || res.status === "unknown") {
        stopPoll(); expired();
      }
    }, 2000);
  }

  function expired() {
    openModal(`
      <div class="authbox">
        <div class="authbox__icon">⌛️</div>
        <div class="authbox__title">${t("auth.expired.title")}</div>
        <div class="authbox__text">${t("auth.expired.text")}</div>
        <button class="btn-tg" id="authGo">${t("auth.retry")}</button>
      </div>`);
  }

  async function logout() {
    try { await post("/api/auth/logout"); } catch (e) {}
    user = null;
    Settings.setFavorites({ league: [], match: [], team: [] });
    emit();
    location.reload();
  }

  /* ------------------------------------------------------------- избранное */
  async function syncFavorites(mergeLocal) {
    if (!user) return;
    try {
      if (mergeLocal) {
        /* Первый вход: то, что человек отметил до появления аккаунта
           (или ещё в старой версии сайта), переносим на сервер. */
        const s = Settings.get();
        const items = [].concat(
          s.favLeagues.map(id => ({ type: "league", id })),
          s.favMatches.map(id => ({ type: "match", id })));
        if (items.length) {
          const res = await post("/api/favorites/merge", { items });
          Settings.setFavorites(res.favorites);
          return;
        }
      }
      const res = await req("/api/favorites");
      Settings.setFavorites(res.favorites);
    } catch (e) { /* без сервера остаёмся на локальной копии */ }
  }

  async function pushFavorite(type, id, on) {
    if (!user) return;
    try { await post("/api/favorites/toggle", { type, id: Number(id) }); }
    catch (e) { /* не критично: локальная копия уже обновлена, догонит при следующем входе */ }
  }

  async function setNotifications(enabled) {
    if (!user) return;
    user.notifications = enabled;
    try { await post("/api/auth/notifications", { enabled }); }
    catch (e) { user.notifications = !enabled; renderProfile(); }
  }

  /* ------------------------------------------------------------- события */
  document.addEventListener("click", async e => {
    if (e.target.closest("#btnAuth")) {
      if (user) { if (window.App && App.openSettings) App.openSettings(); }
      else login();
      return;
    }
    if (e.target.closest("#authGo") || e.target.closest("#profileLogin")) { login(); return; }
    if (e.target.closest("#authClose") || e.target.matches("#authModal")) { closeModal(); return; }
    if (e.target.closest("#btnLogout")) { logout(); return; }
    const sw = e.target.closest("#swNotify");
    if (sw) {
      const on = !sw.classList.contains("is-on");
      sw.classList.toggle("is-on", on);
      sw.setAttribute("aria-checked", String(on));
      setNotifications(on);
    }
  });

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeModal();
    if (e.key === "Enter" && e.target.id === "swNotify") e.target.click();
  });

  async function init() {
    try {
      const res = await req("/api/auth/me");
      user = res.user;
    } catch (e) { user = null; }
    if (user) await syncFavorites(false);
    emit();
  }

  return {
    init, login, logout, promptLogin, pushFavorite, setNotifications,
    user: () => user,
    onChange(fn) { listeners.push(fn); },
  };
})();
