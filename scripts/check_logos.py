#!/usr/bin/env python
"""Проверка эмблем Лигаи Олӣ: у кого свой файл, у кого логотип из API.

Запуск:  venv/bin/python scripts/check_logos.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import teams_tj as tj  # noqa: E402

GREEN, YELLOW, RED, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def main() -> int:
    if not tj.LOGO_DIR.exists():
        print(f"{RED}нет папки{OFF} {tj.LOGO_DIR}")
        return 1

    found = tj._logos()
    print(f"Папка: {tj.LOGO_DIR}\n")

    own, api = [], []
    for slug, club in tj.CLUBS.items():
        line = f"  {club['ru']:<14} {club['tg']:<14} {slug}"
        (own if slug in found else api).append(line)

    print(f"{GREEN}Своя эмблема ({len(own)}){OFF}")
    print("\n".join(own) if own else "  — пока ни одной")
    print(f"\n{YELLOW}Логотип из API ({len(api)}){OFF}")
    print("\n".join(api) if api else "  — все свои")

    # Файлы, чьё имя не совпало ни с одним клубом: почти всегда опечатка
    known = {p.rsplit("/", 1)[-1] for p in found.values()}
    strays = [f.name for f in sorted(tj.LOGO_DIR.iterdir())
              if f.is_file() and f.suffix.lower() in tj.LOGO_EXTS and f.name not in known]
    if strays:
        print(f"\n{RED}Файлы с непонятным именем ({len(strays)}){OFF}")
        for n in strays:
            print(f"  {n}")
        print("  Имя файла должно совпадать со slug'ом из README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
