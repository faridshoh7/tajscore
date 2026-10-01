-- Tajscore: схема SQLite. Все данные сайта живут здесь, наружу ходит только воркер.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------ Справочники
CREATE TABLE IF NOT EXISTS leagues (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    name_ru       TEXT,
    name_tg       TEXT,
    country       TEXT,
    country_ru    TEXT,
    country_tg    TEXT,
    code          TEXT,
    logo          TEXT,
    flag          TEXT,
    season        INTEGER,
    is_cup        INTEGER DEFAULT 0,
    group_stage   INTEGER DEFAULT 0,
    priority      INTEGER DEFAULT 100
);

CREATE TABLE IF NOT EXISTS teams (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    code     TEXT,
    country  TEXT,
    logo     TEXT,
    founded  INTEGER
);

-- ------------------------------------------------------------------ Матчи
CREATE TABLE IF NOT EXISTS fixtures (
    id            INTEGER PRIMARY KEY,
    league_id     INTEGER NOT NULL,
    season        INTEGER,
    round         TEXT,
    date_utc      TEXT NOT NULL,      -- ISO8601 UTC
    timestamp     INTEGER NOT NULL,   -- unix
    status_short  TEXT,               -- NS/1H/HT/2H/ET/PEN/FT/AET/PST/CANC...
    status_long   TEXT,
    elapsed       INTEGER,
    extra_minute  INTEGER,
    venue_name    TEXT,
    venue_city    TEXT,
    venue_capacity INTEGER,   -- бесплатный тариф её не отдаёт; заполняется вручную
    referee       TEXT,
    home_id       INTEGER,
    away_id       INTEGER,
    home_goals    INTEGER,
    away_goals    INTEGER,
    ht_home INTEGER, ht_away INTEGER,
    ft_home INTEGER, ft_away INTEGER,
    et_home INTEGER, et_away INTEGER,
    pen_home INTEGER, pen_away INTEGER,
    winner        TEXT,               -- home/away/draw/NULL
    detail_synced_at INTEGER DEFAULT 0,   -- когда последний раз тянули события/составы
    updated_at    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fx_ts       ON fixtures(timestamp);
CREATE INDEX IF NOT EXISTS idx_fx_league   ON fixtures(league_id, season);
CREATE INDEX IF NOT EXISTS idx_fx_status   ON fixtures(status_short);
CREATE INDEX IF NOT EXISTS idx_fx_teams    ON fixtures(home_id, away_id);

-- События матча (голы, карточки, замены, пенальти, VAR)
CREATE TABLE IF NOT EXISTS fixture_events (
    fixture_id   INTEGER NOT NULL,
    idx          INTEGER NOT NULL,
    minute       INTEGER,
    extra        INTEGER,
    team_id      INTEGER,
    player_id    INTEGER,
    player_name  TEXT,
    assist_id    INTEGER,
    assist_name  TEXT,
    type         TEXT,     -- Goal / Card / subst / Var
    detail       TEXT,     -- Normal Goal / Penalty / Yellow Card / Red Card ...
    comments     TEXT,
    PRIMARY KEY (fixture_id, idx)
);

-- Статистика матча: одна строка = один показатель одной команды
CREATE TABLE IF NOT EXISTS fixture_stats (
    fixture_id INTEGER NOT NULL,
    team_id    INTEGER NOT NULL,
    stat_key   TEXT NOT NULL,
    value      TEXT,
    PRIMARY KEY (fixture_id, team_id, stat_key)
);

-- Составы: шапка (схема + тренер)
CREATE TABLE IF NOT EXISTS fixture_lineups (
    fixture_id  INTEGER NOT NULL,
    team_id     INTEGER NOT NULL,
    formation   TEXT,
    coach_name  TEXT,
    coach_photo TEXT,
    PRIMARY KEY (fixture_id, team_id)
);

-- Составы: игроки (старт + скамейка)
CREATE TABLE IF NOT EXISTS fixture_players (
    fixture_id INTEGER NOT NULL,
    team_id    INTEGER NOT NULL,
    player_id  INTEGER NOT NULL,
    name       TEXT,
    number     INTEGER,
    pos        TEXT,     -- G/D/M/F
    grid       TEXT,     -- "1:1" позиция на поле
    is_start   INTEGER DEFAULT 0,
    photo      TEXT,
    PRIMARY KEY (fixture_id, team_id, player_id)
);

-- ------------------------------------------------------------------ Таблицы лиг
CREATE TABLE IF NOT EXISTS standings (
    league_id   INTEGER NOT NULL,
    season      INTEGER NOT NULL,
    group_name  TEXT NOT NULL DEFAULT '',
    team_id     INTEGER NOT NULL,
    rank        INTEGER,
    played      INTEGER, win INTEGER, draw INTEGER, lose INTEGER,
    gf INTEGER, ga INTEGER, gd INTEGER, points INTEGER,
    form        TEXT,
    description TEXT,     -- "Champions League", "Relegation" и т.п.
    home_json   TEXT,
    away_json   TEXT,
    updated_at  INTEGER DEFAULT 0,
    PRIMARY KEY (league_id, season, group_name, team_id)
);

-- Статистика игроков: goals / assists / yellow / red
CREATE TABLE IF NOT EXISTS player_stats (
    league_id  INTEGER NOT NULL,
    season     INTEGER NOT NULL,
    category   TEXT NOT NULL,
    rank       INTEGER NOT NULL,
    player_id  INTEGER,
    name       TEXT,
    photo      TEXT,
    team_id    INTEGER,
    team_name  TEXT,
    team_logo  TEXT,
    value      INTEGER,
    games      INTEGER,
    minutes    INTEGER,
    -- 'calc'  — посчитано локально из событий загруженных матчей
    -- 'fdorg' — импортировано из football-data.org (полнее: весь сезон)
    source     TEXT DEFAULT 'calc',
    PRIMARY KEY (league_id, season, category, rank)
);

-- Русские и таджикские написания имён людей.
-- Клубы и сборные лежат в справочниках (app/names.py, app/teams_tj.py): их
-- названия договорные и правятся руками. А игроков сотни, состав меняется
-- каждый тур, поэтому написание берётся из Wikidata (лицензия CC0) и кэшируется
-- здесь: один и тот же человек запрашивается ровно один раз.
--   ru/tg = NULL и checked_at > 0 — искали и не нашли, повторять незачем.
CREATE TABLE IF NOT EXISTS person_names (
    latin      TEXT PRIMARY KEY,
    ru         TEXT,
    tg         TEXT,
    qid        TEXT,       -- идентификатор Wikidata, чтобы можно было проверить
    checked_at INTEGER DEFAULT 0,
    -- Портрет с Викисклада: путь к уже обрезанному файлу на нашем диске.
    -- Автор и лицензия не показываются, но хранятся: по условиям CC BY-SA
    -- подпись нужна, и если решим её включить — данные уже под рукой.
    photo      TEXT,
    photo_author  TEXT,
    photo_license TEXT,
    photo_checked_at INTEGER DEFAULT 0
);

-- Коэффициенты букмекера на исход матча (1 / X / 2).
-- Живут отдельно от fixtures: приходят из третьего источника, обновляются по
-- своему расписанию и устаревают быстрее всего остального на сайте.
--   url — ссылка на страницу матча у букмекера, туда ведут кнопки.
CREATE TABLE IF NOT EXISTS odds (
    fixture_id INTEGER PRIMARY KEY,
    home       REAL,
    draw       REAL,
    away       REAL,
    event_id   INTEGER,     -- id события у букмекера
    url        TEXT,
    updated_at INTEGER NOT NULL DEFAULT 0
);

-- ------------------------------------------------------------------ Служебное
-- Личные встречи: какие пары уже выкачаны (сами матчи лежат в fixtures)
CREATE TABLE IF NOT EXISTS h2h_pairs (
    pair_key   TEXT PRIMARY KEY,   -- "min-max" id команд
    fetched_at INTEGER DEFAULT 0
);

-- Когда какая задача синхронизации отработала
CREATE TABLE IF NOT EXISTS sync_state (
    key        TEXT PRIMARY KEY,
    last_run   INTEGER DEFAULT 0,
    last_ok    INTEGER DEFAULT 0,
    last_error TEXT,
    note       TEXT
);

-- Журнал обращений к API — из него считается дневной расход
CREATE TABLE IF NOT EXISTS api_calls (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    day      TEXT NOT NULL,     -- YYYY-MM-DD по UTC (как считает api-sports)
    ts       INTEGER NOT NULL,
    task     TEXT,
    endpoint TEXT,
    params   TEXT,
    status   INTEGER,
    results  INTEGER,
    remaining INTEGER,
    error    TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_day ON api_calls(day);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ------------------------------------------------------------------ Посещения
-- Журнал заходов для админки. IP — персональные данные: храним ограниченный срок,
-- чистка в app/admin.py. Статика и запросы к /api сюда не попадают.
CREATE TABLE IF NOT EXISTS visits (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER NOT NULL,
    ip      TEXT,
    path    TEXT,
    ua      TEXT,
    ref     TEXT,
    country TEXT
);
CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits(ts);
CREATE INDEX IF NOT EXISTS idx_visits_ip ON visits(ip);

-- ------------------------------------------------------------------ Пользователи
-- Регистрация и вход идут только через Telegram-бота (@tajscoreregbot).
-- Пароля у пользователя нет вовсе: подтверждением личности служит сам факт,
-- что человек нажал Start в боте по одноразовой ссылке из своего браузера.
CREATE TABLE IF NOT EXISTS users (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id           INTEGER NOT NULL UNIQUE,
    display_name          TEXT NOT NULL,        -- first_name + last_name из профиля Telegram
    username              TEXT,                 -- без @, может отсутствовать
    -- Телефон получен через request_contact. Персональные данные: наружу
    -- (в API сайта, в шаблоны) не отдаётся никогда, только в админский CSV.
    phone                 TEXT,
    notifications_enabled INTEGER NOT NULL DEFAULT 1,
    created_at            INTEGER NOT NULL,
    last_login            INTEGER NOT NULL DEFAULT 0,
    -- 1 = пользователь заблокировал бота; рассылка его пропускает,
    -- сбрасывается в 0, как только он снова что-то напишет
    is_blocked            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_created  ON users(created_at);

-- Одноразовый токен из deep-link: t.me/<bot>?start=<token>.
-- Живёт 5 минут и привязан к конкретной сессии браузера — чужой человек,
-- перехвативший ссылку, залогинит нашу сессию, а не свою, но и это отсекается
-- сверкой session_id при опросе.
CREATE TABLE IF NOT EXISTS login_tokens (
    token       TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    telegram_id INTEGER,               -- кто подтвердил, заполняет бот
    confirmed   INTEGER NOT NULL DEFAULT 0,
    used        INTEGER NOT NULL DEFAULT 0,   -- сайт забрал результат, повторно не сработает
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tokens_session ON login_tokens(session_id);
CREATE INDEX IF NOT EXISTS idx_tokens_exp     ON login_tokens(expires_at);

-- Сессия браузера. Идентификатор лежит в httpOnly-cookie, в JS недоступен.
-- Сессия заводится ещё до входа (чтобы было к чему привязать login-токен),
-- user_id проставляется в момент подтверждения.
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_exp  ON sessions(expires_at);

-- Избранное авторизованных пользователей. У гостя избранного нет —
-- ему предлагается войти.
CREATE TABLE IF NOT EXISTS favorites (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL CHECK (type IN ('team','league','match')),
    item_id    INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, type, item_id)
);

-- ------------------------------------------------------------------ Устройства
-- Каждое устройство получает UUID-куку при первом заходе. Одно устройство с
-- разными IP — один пользователь. Имя устройства парсится из User-Agent.
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY,
    device_name  TEXT,               -- краткое имя из UA: "iPhone 15 / Safari", "Windows / Chrome"
    ua           TEXT,               -- полный User-Agent (для отладки)
    first_seen   INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL,
    visits       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_devices_last ON devices(last_seen);
