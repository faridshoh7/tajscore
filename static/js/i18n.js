/* Словарь переводов. Добавить строку = добавить ключ в оба языка.

   Таджикский здесь — не подстрочник с русского. Там, где дословный перевод
   читается канцелярски («Мавзӯъ» вместо «Намуд» для темы оформления,
   «Шакл» вместо «Ҳолат» для формы команды), выбрано слово, которое человек
   действительно скажет про футбол. Подписи в таблице — по первой букве
   таджикского слова: Б(озӣ), Ғ(алаба), Д(уранг), М(ағлубият), Х(ол). */
window.I18N = {
  ru: {
    "nav.matches": "Матчи", "nav.live": "Live", "nav.leagues": "Лиги",
    "nav.favorites": "Избранное", "nav.popular": "Популярное",
    "search.placeholder": "Поиск команд и лиг",
    "search.leagues": "Лиги", "search.teams": "Команды", "search.matches": "Матчи",
    "search.empty": "Ничего не найдено",

    "tab.live": "LIVE", "tab.all": "Все", "tab.today": "Сегодня",
    "tab.tomorrow": "Завтра", "tab.yesterday": "Вчера",

    "empty.matches": "Матчей нет",
    "empty.matches.hint": "На этот день в выбранных лигах матчи не назначены",
    "empty.live": "Сейчас нет живых матчей",
    "empty.live.hint": "Как только начнётся игра, счёт появится здесь сам",
    "empty.favorites": "Пока пусто",
    "empty.favorites.hint": "Нажмите звёздочку у матча, команды или лиги — они соберутся здесь",
    "empty.table": "Таблица пока пустая",
    "empty.table.hint": "Она заполнится, когда в этом сезоне пройдут первые матчи",
    "empty.events": "События матча недоступны",
    "empty.lineups": "Составы не опубликованы",
    "empty.stats": "Статистика недоступна",
    "empty.players": "Данных пока нет",
    "empty.players.hint": "Бомбардиры считаются по сыгранным матчам — список появится после первых голов",

    "auth.login": "Войти",
    /* Кнопка в шапке узкая (на телефоне 92 px), поэтому надпись там своя:
       по-таджикски «Ворид шудан» в неё не помещается и наезжает на логотип. */
    "auth.login.short": "Войти",
    "auth.login.tg": "Войти через Telegram",
    "auth.profile": "Профиль",
    "auth.logout": "Выйти",
    "auth.notify": "Уведомления о матчах",
    "auth.guest.hint": "Войдите через Telegram, чтобы сохранять любимые команды и лиги и получать уведомления о матчах.",
    "auth.need.title": "Нужен вход",
    "auth.need.text": "Избранное хранится в вашем аккаунте. Вход занимает пару секунд — через Telegram, без пароля.",
    "auth.wait.title": "Ждём подтверждения",
    "auth.wait.text": "Откройте бота, нажмите Start и поделитесь номером. Эта вкладка войдёт сама.",
    "auth.wait.timer": "Ссылка действует ещё",
    "auth.open.bot": "Открыть бота",
    "auth.done": "Вы вошли",
    "auth.expired.title": "Ссылка устарела",
    "auth.expired.text": "Ссылка для входа живёт 5 минут. Попробуйте ещё раз.",
    "auth.retry": "Войти заново",
    "auth.error": "Не получилось начать вход. Попробуйте позже.",
    "empty.favorites.guest": "Избранное после входа",
    "empty.favorites.guest.hint": "Войдите через Telegram, чтобы отмечать команды, лиги и матчи",

    "settings.title": "Настройки", "settings.theme": "Оформление",
    "settings.theme.dark": "Тёмное", "settings.theme.light": "Светлое",
    "settings.lang": "Язык", "settings.tz": "Часовой пояс",
    "settings.timeformat": "Формат времени", "settings.favleagues": "Избранные лиги",
    "settings.about": "О сайте",

    "status.fixtures": "Матчей в базе",
    "status.teams": "Команд",
    "status.requests": "Запросов к источнику сегодня",
    "status.sync": "Синхронизация",
    "status.sync.on": "работает",
    "status.sync.off": "остановлена",
    "status.livemode": "live-режим",

    "match.events": "Обзор", "match.stats": "Статистика", "match.lineups": "Составы",
    "match.h2h": "Личные встречи", "match.form": "Форма команд",
    "match.starting": "Стартовый состав", "match.bench": "Запасные", "match.coach": "Тренер",
    "match.referee": "Судья", "match.venue": "Стадион", "match.ht": "Первый тайм",
    "match.pens": "Серия пенальти", "match.last5": "Последние матчи",

    "league.table": "Таблица", "league.fixtures": "Календарь", "league.results": "Результаты",
    "league.players": "Игроки", "league.bracket": "Плей-офф", "league.groups": "Группы",
    "dow.0": "вс", "dow.1": "пн", "dow.2": "вт", "dow.3": "ср",
    "dow.4": "чт", "dow.5": "пт", "dow.6": "сб",
    "nav.home": "На главную", "nav.back": "Назад",
    "team.founded": "Основан", "team.matches": "Матчи команды",
    "team.city": "Город",
    "league.season": "Сезон",
    "empty.fixtures": "Ближайших матчей нет",
    "empty.results": "Сыгранных матчей пока нет",
    "league.scorers": "Бомбардиры", "league.assists": "Ассистенты",
    "league.yellow": "Жёлтые карточки", "league.red": "Красные карточки",

    "tbl.pos": "#", "tbl.team": "Команда", "tbl.played": "И", "tbl.win": "В",
    "tbl.draw": "Н", "tbl.lose": "П", "tbl.goals": "Голы", "tbl.gd": "±",
    "tbl.points": "О", "tbl.form": "Форма",

    "zone.ucl": "Лига чемпионов", "zone.uel": "Лига Европы",
    "zone.uecl": "Лига конференций", "zone.playoff": "Стыковые матчи", "zone.releg": "Вылет",
    "zone.acl": "Лига чемпионов АФК", "zone.acl2": "Лига чемпионов АФК-2",

    "status.ns": "", "status.tbd": "?", "status.first_half": "1-й тайм", "status.ht": "Перерыв",
    "status.second_half": "2-й тайм", "status.et": "Доп. время", "status.bt": "Перерыв",
    "status.pen_shootout": "Пенальти", "status.susp": "Приостановлен", "status.int": "Прерван",
    "status.ft": "Матч окончен", "status.aet": "После доп. времени", "status.pen": "По пенальти",
    "status.pst": "Перенесён", "status.canc": "Отменён", "status.abd": "Прерван",
    "status.awd": "Тех. поражение", "status.wo": "Неявка", "status.live": "Идёт",
    "status.short.ft": "Финал", "status.short.ht": "Перерыв",

    "stat.possession": "Владение мячом", "stat.shots_total": "Удары всего",
    "stat.shots_on": "Удары в створ", "stat.shots_off": "Удары мимо",
    "stat.shots_blocked": "Заблокировано", "stat.shots_inside": "Удары из штрафной",
    "stat.shots_outside": "Удары из-за штрафной", "stat.corners": "Угловые",
    "stat.offsides": "Офсайды", "stat.fouls": "Фолы", "stat.yellow": "Жёлтые карточки",
    "stat.red": "Красные карточки", "stat.saves": "Сейвы", "stat.passes": "Передачи",
    "stat.passes_accurate": "Точные передачи", "stat.passes_pct": "Точность передач",
    "stat.xg": "xG (ожидаемые голы)",

    "notice.free": "Таблица считается по матчам, которые собрал сайт. Источник на бесплатном тарифе отдаёт только последние дни, поэтому она заполняется постепенно.",
    "goals.short": "голы", "assists.short": "пасы", "cards.short": "карточки",
    "misc.round": "Тур", "misc.group": "Группа", "misc.all_leagues": "Все лиги",
    "misc.updated": "Обновлено", "misc.today": "Сегодня", "misc.tomorrow": "Завтра",
    "misc.yesterday": "Вчера",

    "a11y.fav": "В избранное", "a11y.close": "Закрыть", "a11y.back": "Назад",
    "ads.label": "Реклама",

    "tz.Asia/Dushanbe": "Душанбе", "tz.Asia/Tashkent": "Ташкент",
    "tz.Asia/Almaty": "Алматы", "tz.Europe/Moscow": "Москва",
    "tz.Europe/Kyiv": "Киев", "tz.Europe/Berlin": "Берлин",
    "tz.Europe/London": "Лондон", "tz.Asia/Dubai": "Дубай",
    "tz.Asia/Istanbul": "Стамбул", "tz.America/New_York": "Нью-Йорк",
    "tz.UTC": "UTC"
  },

  tg: {
    "nav.matches": "Бозиҳо", "nav.live": "Live", "nav.leagues": "Лигаҳо",
    "nav.favorites": "Дӯстдошта", "nav.popular": "Машҳур",
    "search.placeholder": "Ҷустуҷӯи дастаҳо ва лигаҳо",
    "search.leagues": "Лигаҳо", "search.teams": "Дастаҳо", "search.matches": "Бозиҳо",
    "search.empty": "Чизе ёфт нашуд",

    "tab.live": "LIVE", "tab.all": "Ҳама", "tab.today": "Имрӯз",
    "tab.tomorrow": "Пагоҳ", "tab.yesterday": "Дирӯз",

    "empty.matches": "Бозӣ нест",
    "empty.matches.hint": "Барои ин рӯз дар лигаҳои интихобшуда бозӣ таъин нашудааст",
    "empty.live": "Ҳоло бозии зинда нест",
    "empty.live.hint": "Ҳамин ки бозӣ сар шавад, ҳисоб худаш дар ин ҷо пайдо мешавад",
    "empty.favorites": "Ҳанӯз холӣ",
    "empty.favorites.hint": "Ситорачаи назди бозӣ, даста ё лигаро пахш кунед — онҳо дар ин ҷо ҷамъ мешаванд",
    "empty.table": "Ҷадвал ҳанӯз холӣ аст",
    "empty.table.hint": "Пас аз бозиҳои аввали мавсим ҷадвал пур мешавад",
    "empty.events": "Рӯйдодҳои бозӣ дастрас нестанд",
    "empty.lineups": "Ҳайати дастаҳо ҳанӯз эълон нашудааст",
    "empty.stats": "Омор дастрас нест",
    "empty.players": "Ҳанӯз маълумот нест",
    "empty.players.hint": "Гулзанон аз рӯи бозиҳои гузашта ҳисоб мешаванд — рӯйхат пас аз голҳои аввал пайдо мешавад",

    "auth.login": "Ворид шудан",
    "auth.login.short": "Ворид",
    "auth.login.tg": "Бо Telegram ворид шудан",
    "auth.profile": "Профил",
    "auth.logout": "Баромадан",
    "auth.notify": "Огоҳинома дар бораи бозиҳо",
    "auth.guest.hint": "Бо Telegram ворид шавед, то дастаҳо ва лигаҳои дӯстдоштаатон нигоҳ дошта шаванд ва аз бозиҳо огоҳ шавед.",
    "auth.need.title": "Аввал ворид шавед",
    "auth.need.text": "Дӯстдоштаҳо дар ҳисоби шумо нигоҳ дошта мешаванд. Воридшавӣ ҳамагӣ якчанд сония — бо Telegram, бе парол.",
    "auth.wait.title": "Тасдиқро интизорем",
    "auth.wait.text": "Ботро кушоед, Start-ро пахш кунед ва рақами телефонатонро фиристед. Ин саҳифа худаш ворид мешавад.",
    "auth.wait.timer": "Мӯҳлати пайванд:",
    "auth.open.bot": "Кушодани бот",
    "auth.done": "Шумо ворид шудед",
    "auth.expired.title": "Мӯҳлати пайванд гузашт",
    "auth.expired.text": "Пайванди воридшавӣ 5 дақиқа амал мекунад. Бори дигар кӯшиш кунед.",
    "auth.retry": "Аз нав ворид шудан",
    "auth.error": "Воридшавӣ оғоз нашуд. Лутфан, баъдтар кӯшиш кунед.",
    "empty.favorites.guest": "Дӯстдоштаҳо пас аз воридшавӣ",
    "empty.favorites.guest.hint": "Бо Telegram ворид шавед, то дастаҳо, лигаҳо ва бозиҳоро қайд кунед",

    "settings.title": "Танзимот", "settings.theme": "Намуди сайт",
    "settings.theme.dark": "Торик", "settings.theme.light": "Равшан",
    "settings.lang": "Забон", "settings.tz": "Минтақаи вақт",
    "settings.timeformat": "Формати вақт", "settings.favleagues": "Лигаҳои дӯстдошта",
    "settings.about": "Дар бораи сайт",

    "status.fixtures": "Бозиҳо дар пойгоҳ",
    "status.teams": "Дастаҳо",
    "status.requests": "Дархостҳо ба манбаъ имрӯз",
    "status.sync": "Ҳамоҳангсозӣ",
    "status.sync.on": "кор мекунад",
    "status.sync.off": "истодааст",
    "status.livemode": "ҳолати live",

    "match.events": "Шарҳи бозӣ", "match.stats": "Омор", "match.lineups": "Ҳайат",
    "match.h2h": "Вохӯриҳои рӯёрӯ", "match.form": "Ҳолати дастаҳо",
    "match.starting": "Ҳайати асосӣ", "match.bench": "Захира", "match.coach": "Мураббӣ",
    "match.referee": "Довар", "match.venue": "Варзишгоҳ", "match.ht": "Нимаи якум",
    "match.pens": "Зарбаҳои 11-метра", "match.last5": "Бозиҳои охирин",

    "league.table": "Ҷадвал", "league.fixtures": "Тақвим", "league.results": "Натиҷаҳо",
    "league.players": "Бозигарон", "league.bracket": "Плей-офф", "league.groups": "Гурӯҳҳо",
    "dow.0": "яш", "dow.1": "дш", "dow.2": "сш", "dow.3": "чш",
    "dow.4": "пш", "dow.5": "ҷм", "dow.6": "шн",
    "nav.home": "Ба саҳифаи асосӣ", "nav.back": "Бозгашт",
    "team.founded": "Соли таъсис", "team.matches": "Бозиҳои даста",
    "team.city": "Шаҳр",
    "league.season": "Мавсим",
    "empty.fixtures": "Бозии наздик нест",
    "empty.results": "Ҳанӯз бозии анҷомёфта нест",
    "league.scorers": "Гулзанон", "league.assists": "Пасдиҳандагон",
    "league.yellow": "Кортҳои зард", "league.red": "Кортҳои сурх",

    "tbl.pos": "#", "tbl.team": "Даста", "tbl.played": "Б", "tbl.win": "Ғ",
    "tbl.draw": "Д", "tbl.lose": "М", "tbl.goals": "Тӯбҳо", "tbl.gd": "±",
    "tbl.points": "Х", "tbl.form": "Ҳолат",

    "zone.ucl": "Лигаи қаҳрамонон", "zone.uel": "Лигаи Аврупо",
    "zone.uecl": "Лигаи конфронсҳо", "zone.playoff": "Бозиҳои плей-офф",
    "zone.releg": "Хуруҷ аз лига",
    "zone.acl": "Лигаи қаҳрамонони Осиё", "zone.acl2": "Лигаи қаҳрамонони Осиё-2",

    "status.ns": "", "status.tbd": "?", "status.first_half": "Нимаи 1", "status.ht": "Танаффус",
    "status.second_half": "Нимаи 2", "status.et": "Вақти иловагӣ", "status.bt": "Танаффус",
    "status.pen_shootout": "Зарбаҳои 11-метра", "status.susp": "Боздошта шуд",
    "status.int": "Қатъ шуд",
    "status.ft": "Бозӣ тамом", "status.aet": "Пас аз вақти иловагӣ",
    "status.pen": "Бо зарбаҳои 11-метра",
    "status.pst": "Ба таъхир афтод", "status.canc": "Бекор шуд", "status.abd": "Қатъ шуд",
    "status.awd": "Мағлубияти техникӣ", "status.wo": "Ҳозир нашуданд",
    "status.live": "Идома дорад",
    "status.short.ft": "Тамом", "status.short.ht": "Танаффус",

    "stat.possession": "Соҳибии тӯб", "stat.shots_total": "Зарбаҳо",
    "stat.shots_on": "Зарба ба дарвоза", "stat.shots_off": "Зарба аз паҳлӯ",
    "stat.shots_blocked": "Зарбаҳои басташуда", "stat.shots_inside": "Зарба аз ҷаримагоҳ",
    "stat.shots_outside": "Зарба аз берун", "stat.corners": "Зарбаҳои кунҷӣ",
    "stat.offsides": "Офсайд", "stat.fouls": "Қоидавайронкунӣ", "stat.yellow": "Кортҳои зард",
    "stat.red": "Кортҳои сурх", "stat.saves": "Тӯбҳои гирифта", "stat.passes": "Пасҳо",
    "stat.passes_accurate": "Пасҳои дақиқ", "stat.passes_pct": "Дақиқии пасҳо",
    "stat.xg": "xG (голҳои интизорӣ)",

    "notice.free": "Ҷадвал аз рӯи бозиҳое ҳисоб мешавад, ки сайт ҷамъ кардааст. Манбаъ дар тарифи ройгон танҳо рӯзҳои охирро медиҳад, бинобар ин ҷадвал тадриҷан пур мешавад.",
    "goals.short": "голҳо", "assists.short": "пасҳо", "cards.short": "кортҳо",
    "misc.round": "Даври", "misc.group": "Гурӯҳ", "misc.all_leagues": "Ҳама лигаҳо",
    "misc.updated": "Нав шуд", "misc.today": "Имрӯз", "misc.tomorrow": "Пагоҳ",
    "misc.yesterday": "Дирӯз",

    "a11y.fav": "Ба дӯстдоштаҳо", "a11y.close": "Пӯшидан", "a11y.back": "Бозгашт",
    "ads.label": "Реклама",

    "tz.Asia/Dushanbe": "Душанбе", "tz.Asia/Tashkent": "Тошканд",
    "tz.Asia/Almaty": "Алмаато", "tz.Europe/Moscow": "Маскав",
    "tz.Europe/Kyiv": "Киев", "tz.Europe/Berlin": "Берлин",
    "tz.Europe/London": "Лондон", "tz.Asia/Dubai": "Дубай",
    "tz.Asia/Istanbul": "Истанбул", "tz.America/New_York": "Ню-Йорк",
    "tz.UTC": "UTC"
  }
};

window.t = function (key, fallback) {
  const lang = (window.Settings && Settings.get().lang) || "ru";
  const dict = I18N[lang] || I18N.ru;
  if (key in dict) return dict[key];
  if (key in I18N.ru) return I18N.ru[key];
  return fallback !== undefined ? fallback : key;
};

/* Название команды на языке интерфейса.
   Клубы Лигаи Олӣ сервер отдаёт сразу в двух написаниях (см. app/teams_tj.py),
   у остальных name_tg совпадает с name — тогда вернётся то же самое. */
window.tname = function (obj, ruKey, tgKey) {
  if (!obj) return "";
  const lang = (window.Settings && Settings.get().lang) || "ru";
  const ru = obj[ruKey || "name"];
  const tg = obj[tgKey || "name_tg"];
  return (lang === "tg" && tg) ? tg : (ru || tg || "");
};

/* Проставляет переводы во всей разметке: data-i18n, data-i18n-ph, data-i18n-aria */
window.applyI18n = function (root) {
  (root || document).querySelectorAll("[data-i18n]").forEach(el => {
    const v = t(el.dataset.i18n, null);
    if (v !== null) el.textContent = v;
  });
  (root || document).querySelectorAll("[data-i18n-ph]").forEach(el => {
    const v = t(el.dataset.i18nPh, null);
    if (v !== null) el.placeholder = v;
  });
  (root || document).querySelectorAll("[data-i18n-aria]").forEach(el => {
    const v = t(el.dataset.i18nAria, null);
    if (v !== null) { el.setAttribute("aria-label", v); el.setAttribute("title", v); }
  });
  document.documentElement.lang = (window.Settings && Settings.get().lang) || "ru";
};
