/* Рекламный блок под лентой дат.

   Данные приходят из /api/ads (их собирает app/ads.py по data/ads.json).
   Здесь только показ: выбрать креатив под ширину экрана, вставить его,
   раз в полминуты сменить на следующий.

   Размеры места заданы в CSS (.adzone), а не тут: высота считается из
   пропорции, поэтому блок не «прыгает», пока грузится видео. */
window.Ads = (function () {
  const ROTATE_MS = 30000;      // как часто меняется креатив, если их несколько
  const MOBILE_Q = window.matchMedia("(max-width: 860px)");

  let items = [];
  let timer = null;
  let shown = -1;

  const box = () => document.getElementById("adZone");

  /* Взвешенный случайный выбор: weight=2 показывается вдвое чаще weight=1.
     Один и тот же блок подряд не повторяем, пока есть из чего выбрать. */
  function pick() {
    if (items.length === 1) return 0;
    const pool = [];
    items.forEach((it, i) => {
      if (i === shown) return;
      for (let k = 0; k < it.weight; k++) pool.push(i);
    });
    if (!pool.length) return 0;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  /* Маленькая плашка «AD · Реклама»: рекламы нет или она ещё не загрузилась.
     Место под неё всё равно занято — макет не дёргается. */
  function placeholder() {
    const el = box();
    if (!el) return;
    el.className = "adzone adzone--empty";
    el.innerHTML = `<div class="adzone__in">
      <span class="adzone__stub"><b>AD</b><span data-i18n="ads.label">Реклама</span></span>
    </div>`;
    if (window.applyI18n) applyI18n(el);
  }

  function creativeHtml(item) {
    const c = (MOBILE_Q.matches ? item.mobile : item.desktop) || item.desktop;
    if (!c) return "";
    const alt = UI.esc(item.title || "");
    if (c.type === "video") {
      // playsinline + muted — иначе iOS открывает ролик на весь экран и не
      // запускает автовоспроизведение; preload=metadata бережёт мобильный трафик.
      return `<video class="adzone__media" autoplay muted loop playsinline preload="metadata"
        ${c.poster ? `poster="${UI.esc(c.poster)}"` : ""} aria-label="${alt}"></video>`;
    }
    return `<img class="adzone__media" src="${UI.esc(c.src)}" alt="${alt}" loading="lazy">`;
  }

  function show(i) {
    const el = box();
    if (!el || !items[i]) return;
    const item = items[i];
    shown = i;

    const inner = `<div class="adzone__in">
      <span class="adzone__tag" data-i18n="ads.label">Реклама</span>
      ${creativeHtml(item)}
    </div>`;

    el.className = "adzone adzone--live";
    el.innerHTML = item.link
      ? `<a class="adzone__link" href="${UI.esc(item.link)}" target="_blank" rel="nofollow noopener sponsored">${inner}</a>`
      : inner;

    // src у <video> ставим из JS: атрибут в строке заставлял браузер грузить
    // ролик ещё до вставки в документ, даже если креатив тут же сменится.
    const v = el.querySelector("video.adzone__media");
    if (v) {
      const c = (MOBILE_Q.matches ? item.mobile : item.desktop) || item.desktop;
      v.src = c.src;
      const p = v.play();
      // Автозапуск может быть запрещён (экономия трафика в системе) — тогда
      // остаётся постер, и это нормально: ошибку промиса надо съесть.
      if (p && p.catch) p.catch(() => {});
    }
    if (window.applyI18n) applyI18n(el);
  }

  function rotate() {
    clearTimeout(timer);
    if (items.length < 2) return;
    timer = setTimeout(() => { show(pick()); rotate(); }, ROTATE_MS);
  }

  async function load() {
    if (!box()) return;
    placeholder();
    let data;
    try {
      data = await API.ads();
    } catch (e) { return; }          // сети нет — остаётся заглушка
    items = (data && data.enabled && data.items) || [];
    if (!items.length) return;
    show(pick());
    rotate();
  }

  function init() {
    if (!box()) return;
    load();
    // Смена ширины экрана (поворот телефона, окно на десктопе) меняет креатив.
    const onQuery = () => { if (items.length) show(shown < 0 ? pick() : shown); };
    MOBILE_Q.addEventListener ? MOBILE_Q.addEventListener("change", onQuery)
                              : MOBILE_Q.addListener(onQuery);
    document.addEventListener("tajscore:settings", () => { if (items.length) show(shown); });
  }

  return { init, load };
})();
