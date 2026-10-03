/* Уведомления: раздел в настройках, окно тонкой настройки, push на этом
   устройстве и колокольчик на странице матча.

   Уведомления приходят по избранному: звёздочка у команды, лиги или матча =
   подписка. Здесь человек решает, ЧТО из этого присылать и КУДА. */
window.Notify = (function () {
  const $ = s => document.querySelector(s);
  const esc = s => UI.esc(s);
  let state = null;          // ответ /api/notify/prefs
  let saveTimer = null, pendingPatch = {};
  const bells = {};          // fixture_id -> {following, muted, enabled}

  const EVENT_ICONS = {
    reminder: "⏰", lineups: "📋", kickoff: "▶️", goal: "⚽", goal_cancelled: "❌",
    red_card: "🟥", halftime: "⏸", fulltime: "🏁", postponed: "⚠️"
  };

  async function req(path, body) {
    const opts = { headers: { "Content-Type": "application/json", "Accept": "application/json" },
                   credentials: "same-origin" };
    if (body !== undefined) { opts.method = "POST"; opts.body = JSON.stringify(body); }
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  /* ------------------------------------------------------------- push в этом браузере */
  const pushSupported = () =>
    "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent);
  const isStandalone = () =>
    matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  function b64ToBytes(b64) {
    const pad = "=".repeat((4 - b64.length % 4) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, c => c.charCodeAt(0));
  }

  async function currentSub() {
    if (!pushSupported()) return null;
    try {
      const reg = await navigator.serviceWorker.ready;
      return await reg.pushManager.getSubscription();
    } catch (e) { return null; }
  }

  /* Включить push на этом устройстве. Возвращает "ok" | "denied" | "unsupported" | "ios" | "error". */
  async function enablePush() {
    if (!pushSupported()) return isIOS() && !isStandalone() ? "ios" : "unsupported";
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return "denied";
    try {
      const { key } = await req("/api/push/key");
      const reg = await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({ userVisibleOnly: true,
                                                applicationServerKey: b64ToBytes(key) });
      }
      const res = await req("/api/push/subscribe", { subscription: sub.toJSON() });
      if (state) state.push_devices = res.push_devices;
      return "ok";
    } catch (e) { return "error"; }
  }

  async function disablePush() {
    const sub = await currentSub();
    if (!sub) return;
    try {
      const res = await req("/api/push/unsubscribe", { endpoint: sub.endpoint });
      if (state) state.push_devices = res.push_devices;
    } catch (e) {}
    try { await sub.unsubscribe(); } catch (e) {}
  }

  /* ------------------------------------------------------------- сохранение */
  function deepMerge(a, b) {
    const out = Object.assign({}, a);
    Object.keys(b).forEach(k => {
      out[k] = (b[k] && typeof b[k] === "object" && !Array.isArray(b[k]))
        ? deepMerge(a[k] || {}, b[k]) : b[k];
    });
    return out;
  }

  /* Изменения копятся и уходят одним запросом через полсекунды:
     щёлкать переключателями можно быстро, сервер это не нагружает. */
  function patch(p) {
    if (!state) return;
    state.prefs = deepMerge(state.prefs, p);
    pendingPatch = deepMerge(pendingPatch, p);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flush, 500);
  }

  async function flush() {
    const p = Object.assign({}, pendingPatch, { lang: Settings.get().lang, tz: Settings.get().tz });
    pendingPatch = {};
    try { state = await req("/api/notify/prefs", { prefs: p }); }
    catch (e) { toast(t("notify.save.error")); }
  }

  async function setEnabled(on) {
    if (!state) return;
    state.enabled = on;
    try {
      state = await req("/api/notify/prefs", { enabled: on,
        prefs: { lang: Settings.get().lang, tz: Settings.get().tz } });
      const u = window.Auth && Auth.user();
      if (u) u.notifications = on;
    } catch (e) { state.enabled = !on; }
    renderSection(); renderModal();
  }

  async function load() {
    if (!window.Auth || !Auth.user()) { state = null; renderSection(); return; }
    try { state = await req("/api/notify/prefs"); } catch (e) { state = null; }
    renderSection();
  }

  /* ------------------------------------------------------------- раздел в настройках */
  async function renderSection() {
    const box = $("#notifySection");
    if (!box) return;
    if (!window.Auth || !Auth.user()) {
      box.innerHTML = `
        <div class="drawer__label">${esc(t("notify.title"))}</div>
        <div class="notify-card">
          <div class="notify-card__icon">🔔</div>
          <div class="notify-card__text">${esc(t("notify.guest"))}</div>
        </div>
        <button class="btn-tg" id="notifyLogin">${esc(t("auth.login.tg"))}</button>`;
      return;
    }
    if (!state) { box.innerHTML = `<div class="drawer__label">${esc(t("notify.title"))}</div>`; return; }
    const sub = await currentSub();
    const tgOn = state.prefs.channels.telegram && !state.telegram.blocked;
    const pushOn = state.prefs.channels.push && !!sub;
    box.innerHTML = `
      <div class="drawer__label">${esc(t("notify.title"))}</div>
      <label class="switch-row">
        <span>${esc(t("notify.master"))}</span>
        <span class="switch${state.enabled ? " is-on" : ""}" data-nswitch="master" role="switch"
              aria-checked="${state.enabled}" tabindex="0"></span>
      </label>
      <div class="notify-status">
        <span class="chip${tgOn && state.enabled ? " chip--on" : ""}">✈️ Telegram</span>
        <span class="chip${pushOn && state.enabled ? " chip--on" : ""}">📱 ${esc(t("notify.this_device"))}</span>
      </div>
      <button class="btn-outline" id="notifyOpen">${esc(t("notify.configure"))}</button>`;
  }

  /* ------------------------------------------------------------- окно настройки */
  function modalEl() {
    let m = $("#notifyModal");
    if (m) return m;
    m = document.createElement("div");
    m.className = "modal";
    m.id = "notifyModal";
    m.setAttribute("aria-hidden", "true");
    m.innerHTML = `<div class="modal__box modal__box--wide" role="dialog" aria-modal="true">
        <button class="icon-btn modal__close" id="notifyClose" aria-label="${esc(t("a11y.close"))}">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
        <div id="notifyBody"></div></div>`;
    document.body.appendChild(m);
    return m;
  }

  function openModal() {
    const m = modalEl();
    renderModal();
    m.classList.add("is-open");
    m.setAttribute("aria-hidden", "false");
  }

  function closeModal() {
    const m = $("#notifyModal");
    if (!m) return;
    m.classList.remove("is-open");
    m.setAttribute("aria-hidden", "true");
    renderSection();
  }

  const sw = (key, on, extra) =>
    `<span class="switch${on ? " is-on" : ""}" data-nswitch="${key}" role="switch"
           aria-checked="${!!on}" tabindex="0"${extra || ""}></span>`;

  const seg = (name, value, options) => `<div class="seg seg--sm" data-nseg="${name}">
      ${options.map(([v, label]) => `<button data-val="${v}" class="${String(v) === String(value) ? "is-active" : ""}">${esc(label)}</button>`).join("")}
    </div>`;

  async function renderModal() {
    const body = $("#notifyBody");
    if (!body || !state) return;
    const p = state.prefs;
    const sub = await currentSub();
    const perm = ("Notification" in window) ? Notification.permission : "unsupported";
    const off = !state.enabled;

    let pushHint = "";
    if (!pushSupported()) pushHint = isIOS() && !isStandalone() ? t("notify.push.ios") : t("notify.push.unsupported");
    else if (perm === "denied") pushHint = t("notify.push.denied");

    const tgHint = state.telegram.blocked
      ? `<div class="notify-hint notify-hint--warn">${esc(t("notify.tg.blocked"))}
           <a href="https://t.me/${esc(window.TG_BOT || "tajscoreregbot")}" target="_blank" rel="noopener">${esc(t("auth.open.bot"))}</a></div>` : "";

    const favs = Settings.get();
    const counts = { teams: (favs.favTeams || []).length, leagues: favs.favLeagues.length,
                     matches: favs.favMatches.length };
    const levels = [["all", t("notify.level.all")], ["key", t("notify.level.key")], ["off", t("notify.level.off")]];

    body.innerHTML = `
      <div class="nset">
        <div class="nset__head">
          <div class="nset__title">🔔 ${esc(t("notify.title"))}</div>
          <label class="switch-row switch-row--strong">
            <span>${esc(t("notify.master"))}</span>${sw("master", state.enabled)}
          </label>
        </div>

        <div class="nset__group${off ? " is-off" : ""}">
          <div class="nset__label">${esc(t("notify.channels"))}</div>
          <label class="switch-row">
            <span>✈️ Telegram <small>${esc(t("notify.tg.hint"))}</small></span>
            ${sw("ch.telegram", p.channels.telegram && !state.telegram.blocked)}
          </label>
          ${tgHint}
          <label class="switch-row">
            <span>📱 ${esc(t("notify.push"))} <small>${esc(t("notify.push.hint"))}${state.push_devices ? " · " + esc(t("notify.push.devices")) + ": " + state.push_devices : ""}</small></span>
            ${sw("ch.push", p.channels.push && !!sub && perm === "granted")}
          </label>
          ${pushHint ? `<div class="notify-hint">${esc(pushHint)}</div>` : ""}
        </div>

        <div class="nset__group${off ? " is-off" : ""}">
          <div class="nset__label">${esc(t("notify.events"))}</div>
          ${state.options.events.map(ev => `
            <label class="switch-row">
              <span>${EVENT_ICONS[ev] || "•"} ${esc(t("notify.ev." + ev))}
                ${state.options.key_events.includes(ev) ? "" : `<small>${esc(t("notify.ev.detail"))}</small>`}</span>
              ${sw("ev." + ev, p.events[ev])}
            </label>`).join("")}
          <div class="nset__row">
            <span>⏰ ${esc(t("notify.reminder_min"))}</span>
            ${seg("reminder_min", p.reminder_min, state.options.reminder_min.map(v => [v, v >= 60 ? (v / 60) + " " + t("notify.h") : v + " " + t("notify.min")]))}
          </div>
        </div>

        <div class="nset__group${off ? " is-off" : ""}">
          <div class="nset__label">${esc(t("notify.sources"))}</div>
          <div class="notify-hint">${esc(t("notify.sources.hint"))}</div>
          ${["teams", "matches", "leagues"].map(k => `
            <div class="nset__row nset__row--col">
              <span>${k === "teams" ? "👕" : k === "matches" ? "⚽" : "🏆"} ${esc(t("notify.src." + k))}
                <small>${esc(t("notify.src.count"))}: ${counts[k]}</small></span>
              ${seg("src." + k, p.sources[k], levels)}
            </div>`).join("")}
        </div>

        <div class="nset__group${off ? " is-off" : ""}">
          <div class="nset__label">${esc(t("notify.quiet"))}</div>
          <label class="switch-row">
            <span>🌙 ${esc(t("notify.quiet.on"))}</span>${sw("quiet.enabled", p.quiet.enabled)}
          </label>
          <div class="nset__row${p.quiet.enabled ? "" : " is-off"}">
            <span>${esc(t("notify.quiet.from"))}</span>
            <input class="select select--time" type="time" data-ntime="from" value="${esc(p.quiet.from)}">
            <span>${esc(t("notify.quiet.to"))}</span>
            <input class="select select--time" type="time" data-ntime="to" value="${esc(p.quiet.to)}">
          </div>
          <div class="nset__row${p.quiet.enabled ? "" : " is-off"}">
            ${seg("quiet.mode", p.quiet.mode, [["silent", t("notify.quiet.silent")], ["skip", t("notify.quiet.skip")]])}
          </div>
        </div>

        <div class="nset__foot">
          <button class="btn-tg" id="notifyTest">${esc(t("notify.test"))}</button>
          <div class="notify-hint" id="notifyTestRes"></div>
        </div>
      </div>`;
  }

  /* ------------------------------------------------------------- колокольчик на странице матча */
  function bellHtml(fid) {
    if (!window.Auth || !Auth.user()) {
      return `<button class="bell" data-bell="${fid}" data-bell-act="login">🔔 <span>${esc(t("notify.bell.follow"))}</span></button>`;
    }
    const b = bells[fid];
    if (!b) return "";
    if (!b.enabled) return `<button class="bell" data-bell="${fid}" data-bell-act="settings">🔕 <span>${esc(t("notify.bell.disabled"))}</span></button>`;
    if (b.following && !b.muted)
      return `<button class="bell is-on" data-bell="${fid}" data-bell-act="mute">🔔 <span>${esc(t("notify.bell.on"))}</span></button>`;
    if (b.following && b.muted)
      return `<button class="bell" data-bell="${fid}" data-bell-act="unmute">🔕 <span>${esc(t("notify.bell.muted"))}</span></button>`;
    return `<button class="bell" data-bell="${fid}" data-bell-act="follow">🔔 <span>${esc(t("notify.bell.follow"))}</span></button>`;
  }

  async function loadBell(fid) {
    if (!window.Auth || !Auth.user()) { paintBell(fid); return; }
    try {
      const r = await req("/api/notify/match/" + fid);
      if (r.auth) bells[fid] = r;
    } catch (e) {}
    paintBell(fid);
  }

  function paintBell(fid) {
    const box = $("#matchBell");
    if (box) box.innerHTML = bellHtml(fid);
  }

  async function bellAction(fid, act) {
    if (act === "login") { Auth.promptLogin(); return; }
    if (act === "settings") { if (window.App) App.openSettings(); openModal(); return; }
    if (act === "follow") {
      // Подписаться на матч = добавить его в избранное
      if (!Settings.isFavMatch(fid)) Settings.toggleFavMatch(fid);
      await req("/api/notify/mute", { fixture_id: fid, muted: false }).catch(() => {});
      toast(t("notify.bell.followed"));
    } else {
      await req("/api/notify/mute", { fixture_id: fid, muted: act === "mute" }).catch(() => {});
      toast(t(act === "mute" ? "notify.bell.muted_toast" : "notify.bell.on"));
    }
    setTimeout(() => loadBell(fid), 400);
  }

  /* ------------------------------------------------------------- всплывашка */
  function toast(text) {
    let el = $("#toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast"; el.className = "toast"; el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.classList.add("is-on");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("is-on"), 2600);
  }

  /* ------------------------------------------------------------- события */
  async function onSwitch(key, on) {
    if (key === "master") { setEnabled(on); return; }
    if (key === "ch.push") {
      if (on) {
        const res = await enablePush();
        if (res !== "ok") {
          toast(t("notify.push." + (res === "denied" ? "denied" : res === "ios" ? "ios" : "unsupported")));
          renderModal(); return;
        }
        patch({ channels: { push: true } });
        toast(t("notify.push.enabled"));
      } else {
        await disablePush();
        patch({ channels: { push: false } });
      }
      renderModal(); return;
    }
    const [group, name] = key.split(".");
    if (group === "ch") patch({ channels: { [name]: on } });
    if (group === "ev") patch({ events: { [name]: on } });
    if (group === "quiet") patch({ quiet: { [name]: on } });
    renderModal();
  }

  document.addEventListener("click", async e => {
    if (e.target.closest("#notifyLogin")) { Auth.login(); return; }
    if (e.target.closest("#notifyOpen")) { openModal(); return; }
    if (e.target.closest("#notifyClose") || e.target.matches("#notifyModal")) { closeModal(); return; }
    const s = e.target.closest("[data-nswitch]");
    if (s) { onSwitch(s.dataset.nswitch, !s.classList.contains("is-on")); return; }
    const segBtn = e.target.closest("[data-nseg] button");
    if (segBtn) {
      const name = segBtn.parentElement.dataset.nseg, v = segBtn.dataset.val;
      if (name === "reminder_min") patch({ reminder_min: Number(v) });
      else if (name.startsWith("src.")) patch({ sources: { [name.slice(4)]: v } });
      else if (name === "quiet.mode") patch({ quiet: { mode: v } });
      renderModal(); return;
    }
    if (e.target.closest("#notifyTest")) {
      const out = $("#notifyTestRes");
      if (out) out.textContent = "…";
      clearTimeout(saveTimer); await flush();
      try {
        const r = await req("/api/notify/test", {});
        const bits = [];
        if (r.telegram) bits.push("✈️ Telegram ✓");
        if (r.push) bits.push("📱 Push ✓ (" + r.push + ")");
        if (out) out.textContent = bits.length ? bits.join(" · ") : t("notify.test.none");
      } catch (err) { if (out) out.textContent = t("notify.save.error"); }
      return;
    }
    const bell = e.target.closest("[data-bell]");
    if (bell) bellAction(Number(bell.dataset.bell), bell.dataset.bellAct);
  });

  document.addEventListener("change", e => {
    const ti = e.target.closest("[data-ntime]");
    if (ti && /^\d{2}:\d{2}$/.test(ti.value)) patch({ quiet: { [ti.dataset.ntime]: ti.value } });
  });

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeModal();
    if (e.key === "Enter" && e.target.matches("[data-nswitch]")) e.target.click();
  });

  /* Язык и пояс уведомлений следуют за настройками сайта */
  document.addEventListener("tajscore:settings", () => {
    if (state) patch({});
    renderSection(); renderModal();
  });

  function init() {
    if (window.Auth) Auth.onChange(() => { load(); });
    // ссылка из бота «Настроить на сайте»: /?notify=1
    if (new URLSearchParams(location.search).get("notify") === "1") {
      const tryOpen = () => {
        if (window.Auth && Auth.user() && state) {
          if (window.App) App.openSettings();
          openModal();
        } else if (window.Auth && Auth.user() === null && document.readyState === "complete") {
          if (window.App) App.openSettings();
        }
      };
      setTimeout(tryOpen, 1200);
    }
  }

  return { init, load, open: openModal, bellHtml, loadBell, toast, enablePush };
})();
