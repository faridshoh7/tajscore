/* Приложение Tajscore: регистрация сервис-воркера и кнопка «Установить».

   На Android/компьютере браузер сам предлагает установку (beforeinstallprompt) —
   мы ловим это событие и показываем свою кнопку в настройках и небольшую
   плашку на главной. На iPhone такого события нет: там показываем подсказку
   «Поделиться → На экран „Домой“». */
window.PWA = (function () {
  const $ = s => document.querySelector(s);
  const KEY = "tajscore.install";
  let deferred = null;

  const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent);
  const standalone = () =>
    matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  function store() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; }
  }
  function save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) {} }

  function canOffer() { return !standalone() && (deferred || isIOS()); }

  function renderSection() {
    const box = $("#installSection");
    if (!box) return;
    if (!canOffer()) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `
      <div class="drawer__label">${UI.esc(t("pwa.title"))}</div>
      <div class="notify-card">
        <img class="notify-card__app" src="/static/img/icon-192.png" alt="">
        <div class="notify-card__text">${UI.esc(t(isIOS() && !deferred ? "pwa.ios" : "pwa.text"))}</div>
      </div>
      ${deferred ? `<button class="btn-tg" data-install>${UI.esc(t("pwa.install"))}</button>` : ""}`;
  }

  /* Плашка на главной — со второго визита, и если человек её не закрывал */
  function maybeBanner() {
    if (!canOffer() || document.body.querySelector(".pwa-banner")) return;
    const s = store();
    if (s.dismissed && Date.now() - s.dismissed < 14 * 86400000) return;
    if ((s.visits || 0) < 2) return;
    if (location.pathname !== "/") return;
    const el = document.createElement("div");
    el.className = "pwa-banner";
    el.innerHTML = `
      <img src="/static/img/icon-192.png" alt="">
      <div class="pwa-banner__text"><b>Tajscore</b><span>${UI.esc(t(isIOS() && !deferred ? "pwa.ios.short" : "pwa.banner"))}</span></div>
      ${deferred ? `<button class="pwa-banner__btn" data-install>${UI.esc(t("pwa.install.short"))}</button>` : ""}
      <button class="pwa-banner__close" data-install-close aria-label="${UI.esc(t("a11y.close"))}">✕</button>`;
    document.body.appendChild(el);
  }

  async function install() {
    if (!deferred) return;
    deferred.prompt();
    const { outcome } = await deferred.userChoice;
    deferred = null;
    if (outcome === "accepted") save({ ...store(), installed: Date.now() });
    document.querySelector(".pwa-banner")?.remove();
    renderSection();
  }

  document.addEventListener("click", e => {
    if (e.target.closest("[data-install]")) { install(); return; }
    if (e.target.closest("[data-install-close]")) {
      save({ ...store(), dismissed: Date.now() });
      document.querySelector(".pwa-banner")?.remove();
    }
  });

  window.addEventListener("beforeinstallprompt", e => {
    e.preventDefault();          // своя кнопка вместо навязчивого системного окна
    deferred = e;
    renderSection();
    maybeBanner();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    save({ ...store(), installed: Date.now() });
    document.querySelector(".pwa-banner")?.remove();
    renderSection();
  });
  document.addEventListener("tajscore:settings", renderSection);

  function init() {
    const s = store();
    s.visits = (s.visits || 0) + 1;
    save(s);
    if ("serviceWorker" in navigator) {
      // После загрузки страницы: регистрация не должна тормозить первый показ
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
      });
    }
    renderSection();
    if (isIOS()) setTimeout(maybeBanner, 4000);
  }

  return { init, install, standalone };
})();
