"""Слияние задвоившихся команд.

Два источника называют клубы по-разному («Leeds» и «Leeds United FC»,
«Man City» и «Manchester City»), поэтому одна команда может попасть в базу
дважды. Скрипт находит такие пары и склеивает их.

Запуск:
    ./venv/bin/python scripts/merge_dupes.py          # только показать
    ./venv/bin/python scripts/merge_dupes.py --apply  # выполнить слияние

Защита от ложных срабатываний: если команды играли друг с другом
(«Los Angeles FC» и «Los Angeles Galaxy»), это разные клубы — не сливаем.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import analytics, db
from app.sync.fdorg import TEAM_OFFSET, normalize

APPLY = "--apply" in sys.argv


def words(name: str) -> list[str]:
    return normalize(name).split()


def _same_word(w: str, x: str) -> bool:
    """Совпадение слов: точное либо префиксное с заметной разницей длины.

    «man» ~ «manchester» — сокращение, разница 7 букв.
    «bayer» и «bayern» — РАЗНЫЕ клубы (Леверкузен и Мюнхен), разница 1 буква.
    Поэтому префикс засчитывается только при разнице от двух символов.
    """
    if w == x:
        return True
    short, long = (w, x) if len(w) < len(x) else (x, w)
    return len(short) >= 3 and len(long) - len(short) >= 2 and long.startswith(short)


def same_club(a: str, b: str) -> bool:
    """Каждое слово короткого имени должно найтись в длинном."""
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    short, long = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return all(any(_same_word(w, x) for x in long) for w in short)


def played_each_other(a: int, b: int) -> bool:
    return bool(db.query_one(
        """SELECT 1 FROM fixtures WHERE (home_id=? AND away_id=?) OR (home_id=? AND away_id=?)
           LIMIT 1""", (a, b, b, a)))


# Команды сгруппированы по лигам: сливать имеет смысл только внутри одной лиги
league_teams: dict[int, set[int]] = {}
for r in db.query("""SELECT DISTINCT league_id, home_id tid FROM fixtures WHERE home_id IS NOT NULL
                     UNION SELECT DISTINCT league_id, away_id FROM fixtures WHERE away_id IS NOT NULL"""):
    league_teams.setdefault(r["league_id"], set()).add(r["tid"])

names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM teams")}
pairs, seen = [], set()

for lid, tids in league_teams.items():
    ids = sorted(tids)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            # одна запись должна быть импортной, другая — «родной» из API-Football
            if (a >= TEAM_OFFSET) == (b >= TEAM_OFFSET):
                continue
            if not same_club(names.get(a, ""), names.get(b, "")):
                continue
            if played_each_other(a, b):
                continue                      # играли между собой → разные клубы
            keep, drop = (a, b) if a < TEAM_OFFSET else (b, a)
            if (keep, drop) in seen:
                continue
            seen.add((keep, drop))
            pairs.append((lid, keep, drop))

# Если импортная запись подошла сразу к нескольким «родным», решить автоматически
# нельзя — такие пары откладываем и показываем отдельно.
from collections import Counter
drop_count = Counter(d for _, _, d in pairs)
keep_count = Counter(k for _, k, _ in pairs)
ambiguous = [p for p in pairs if drop_count[p[2]] > 1 or keep_count[p[1]] > 1]
pairs = [p for p in pairs if p not in ambiguous]

if ambiguous:
    print(f"Пропущено как неоднозначные (нужно решить вручную): {len(ambiguous)}")
    for lid, keep, drop in ambiguous:
        print(f"  лига {lid}: «{names[drop]}» (id {drop})  ~  «{names[keep]}» (id {keep})")
    print()

if not pairs and not APPLY:
    print("Дублей команд для автоматического слияния не найдено.")
    raise SystemExit(0)

print(f"Найдено пар: {len(pairs)}\n")
for lid, keep, drop in pairs:
    print(f"  лига {lid}: оставить «{names[keep]}» (id {keep})  ←  «{names[drop]}» (id {drop})")

if not APPLY:
    print("\nЭто предпросмотр. Для выполнения: ./venv/bin/python scripts/merge_dupes.py --apply")
    raise SystemExit(0)

print("\nСливаю…")
merged = 0
with db.write() as conn:
    for _, keep, drop in pairs:
        # матчи переносим на оставшуюся команду; дубль матча тут не возникает —
        # у каждого матча свой id, а одинаковые пары уже склеены при импорте
        conn.execute("UPDATE OR IGNORE fixtures SET home_id=? WHERE home_id=?", (keep, drop))
        conn.execute("UPDATE OR IGNORE fixtures SET away_id=? WHERE away_id=?", (keep, drop))
        conn.execute("UPDATE OR IGNORE fixture_events SET team_id=? WHERE team_id=?", (keep, drop))
        conn.execute("UPDATE OR IGNORE player_stats SET team_id=? WHERE team_id=?", (keep, drop))
        # у импортной записи бывает логотип там, где у родной пусто
        conn.execute("""UPDATE teams SET logo=COALESCE(logo, (SELECT logo FROM teams WHERE id=?))
                        WHERE id=?""", (drop, keep))
        conn.execute("DELETE FROM standings WHERE team_id=?", (drop,))
        conn.execute("DELETE FROM teams WHERE id=?", (drop,))
        merged += 1

print(f"Слито команд: {merged}")

# ------------------------------------------------------------------ дубли матчей
# Один и тот же матч мог прийти из обоих источников. При импорте он не склеился,
# потому что команды тогда ещё считались разными; после слияния команд такие
# записи стали видны как дубли — теперь их можно убрать.
rows = db.query("""SELECT id, league_id, home_id, away_id, timestamp, round
                   FROM fixtures WHERE home_id IS NOT NULL AND away_id IS NOT NULL""")
groups = {}
for r in rows:
    groups.setdefault((r["league_id"], r["home_id"], r["away_id"], r["timestamp"] // 86400), []).append(r)

removed = 0
with db.write() as conn:
    for items in groups.values():
        if len(items) < 2:
            continue
        # оставляем запись с меньшим id — она из API-Football, к ней привязаны
        # события и составы матча
        items.sort(key=lambda x: x["id"])
        keep, drop = items[0], items[1:]
        # тур есть у импортной записи и отсутствует у родной — переносим
        if not keep["round"]:
            rnd = next((d["round"] for d in drop if d["round"]), None)
            if rnd:
                conn.execute("UPDATE fixtures SET round=? WHERE id=?", (rnd, keep["id"]))
        for d in drop:
            for tbl in ("fixture_events", "fixture_stats", "fixture_lineups", "fixture_players"):
                conn.execute(f"DELETE FROM {tbl} WHERE fixture_id=?", (d["id"],))
            conn.execute("DELETE FROM fixtures WHERE id=?", (d["id"],))
            removed += 1

print(f"Удалено дублей матчей: {removed}")
analytics.recompute_all()
print("Команд в базе:", db.query_one("SELECT COUNT(*) n FROM teams")["n"])
print("Матчей в базе:", db.query_one("SELECT COUNT(*) n FROM fixtures")["n"])
