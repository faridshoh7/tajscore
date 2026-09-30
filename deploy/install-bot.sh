#!/usr/bin/env bash
#
# Установка Telegram-бота Tajscore как systemd-сервиса.
# Запуск:  sudo bash /home/tajscore/tajscore/deploy/install-bot.sh
#
# Скрипт идемпотентен: повторный запуск ничего не ломает.
# Сайт (tajscore.service) не трогается вообще — бот ставится отдельным юнитом.

set -euo pipefail

ROOT="/home/tajscore/tajscore"
DEPLOY_DIR="$ROOT/deploy"
UNIT="/etc/systemd/system/tajscore-bot.service"
VENV="$ROOT/venv"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()  { printf '   \033[32m✓\033[0m %s\n' "$*"; }
err() { printf '   \033[31m✗\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { err "нужен root: sudo bash $0"; exit 1; }

# ---------------------------------------------------------------- 1. .env
say "1/4  проверка .env"

missing=0
for key in TELEGRAM_BOT_TOKEN TELEGRAM_BOT_USERNAME ADMIN_TELEGRAM_ID; do
    # значение должно быть не пустым; сам токен на экран не печатаем
    if ! grep -qE "^${key}=.+" "$ROOT/.env" 2>/dev/null; then
        err "в .env нет непустого $key"
        missing=1
    else
        ok "$key задан"
    fi
done
[ "$missing" -eq 0 ] || { err "заполните $ROOT/.env (образец — .env.example) и запустите скрипт заново"; exit 1; }

# ---------------------------------------------------------------- 2. зависимости
say "2/4  зависимости"

if ! "$VENV/bin/python" -c "import aiogram" 2>/dev/null; then
    sudo -u tajscore "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
    ok "aiogram установлен"
else
    ok "aiogram уже стоит: $("$VENV/bin/python" -c 'import aiogram;print(aiogram.__version__)')"
fi

# Токен проверяем до установки юнита: неверный токен = бесконечный рестарт-луп
say "проверка токена у Telegram"
if ! sudo -u tajscore "$VENV/bin/python" -c "
import asyncio, sys
sys.path.insert(0, '$ROOT')
from aiogram import Bot
from app.config import TELEGRAM_BOT_TOKEN
async def main():
    bot = Bot(TELEGRAM_BOT_TOKEN)
    try:
        me = await bot.get_me()
        print('   \033[32m✓\033[0m Telegram отвечает: @' + me.username)
    finally:
        await bot.session.close()
asyncio.run(main())
"; then
    err "Telegram не принял токен — сервис не ставлю"
    exit 1
fi

# ---------------------------------------------------------------- 3. systemd
say "3/4  systemd-юнит"

# Запущенный вручную бот занял бы long-polling: Telegram отдаёт апдейты
# только одному потребителю, второй получит 409 Conflict
if pgrep -f "python -m bot.main" >/dev/null 2>&1; then
    pkill -f "python -m bot.main" || true
    sleep 2
    ok "остановлен ранее запущенный вручную бот"
fi

install -m 644 "$DEPLOY_DIR/tajscore-bot.service" "$UNIT"
ok "юнит установлен: $UNIT"

systemctl daemon-reload
systemctl enable tajscore-bot.service >/dev/null
ok "автозапуск при загрузке включён"

systemctl restart tajscore-bot.service
sleep 5

# ---------------------------------------------------------------- 4. проверка
say "4/4  проверка"

if ! systemctl is-active --quiet tajscore-bot.service; then
    err "сервис не поднялся, последние строки журнала:"
    journalctl -u tajscore-bot.service -n 30 --no-pager
    exit 1
fi
ok "сервис работает"

if journalctl -u tajscore-bot.service -n 50 --no-pager | grep -q "Бот @"; then
    ok "$(journalctl -u tajscore-bot.service -n 50 --no-pager | grep -o 'Бот @.*' | tail -1)"
else
    err "в журнале нет строки о запуске — посмотрите: journalctl -u tajscore-bot -n 50"
fi

say "Готово"
systemctl --no-pager --lines=0 status tajscore-bot.service | head -10
cat <<'TXT'

Дальше:
  journalctl -u tajscore-bot -f        — живой лог бота
  systemctl restart tajscore-bot       — перезапуск
  В самом боте: /admin (только с ADMIN_TELEGRAM_ID)

Сайт нужно перезапустить один раз, чтобы он подхватил новые роуты входа:
  sudo systemctl restart tajscore
TXT
