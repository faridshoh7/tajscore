#!/usr/bin/env bash
#
# Установка Tajscore: systemd-сервис + nginx reverse proxy.
# Запуск:  sudo bash /home/tajscore/tajscore/deploy/install.sh
#
# Скрипт идемпотентен: повторный запуск ничего не ломает.
# Если nginx -t не проходит — конфиг автоматически откатывается из бэкапа,
# nginx не перезагружается, сайт продолжает работать на старом конфиге.

set -euo pipefail

DEPLOY_DIR="/home/tajscore/tajscore/deploy"
NGINX_CONF="/etc/nginx/sites-available/default"
BACKUP="/etc/nginx/sites-available/default.backup-$(date +%Y%m%d-%H%M%S)"
UNIT="/etc/systemd/system/tajscore.service"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()  { printf '   \033[32m✓\033[0m %s\n' "$*"; }
err() { printf '   \033[31m✗\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { err "нужен root: sudo bash $0"; exit 1; }

# ---------------------------------------------------------------- 1. systemd
say "1/4  systemd-сервис"

# Ручной uvicorn занял бы порт 8000 и сервис не поднялся бы
if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    pkill -f "uvicorn app.main:app" || true
    sleep 2
    ok "остановлен ранее запущенный вручную uvicorn"
fi

install -m 644 "$DEPLOY_DIR/tajscore.service" "$UNIT"
ok "юнит установлен: $UNIT"

systemctl daemon-reload
systemctl enable tajscore.service >/dev/null
ok "автозапуск при загрузке включён"

systemctl restart tajscore.service
sleep 4

if ! systemctl is-active --quiet tajscore.service; then
    err "сервис не поднялся, последние строки журнала:"
    journalctl -u tajscore.service -n 30 --no-pager
    exit 1
fi
ok "сервис запущен"

# Порт должен реально слушаться, иначе проксировать некуда
for i in $(seq 1 10); do
    curl -sf -o /dev/null -m 2 http://127.0.0.1:8000/api/health && break
    [ "$i" -eq 10 ] && { err "127.0.0.1:8000 не отвечает"; journalctl -u tajscore.service -n 30 --no-pager; exit 1; }
    sleep 1
done
ok "приложение отвечает на 127.0.0.1:8000"

# ---------------------------------------------------------------- 2. бэкап
say "2/4  бэкап конфига nginx"
cp -a "$NGINX_CONF" "$BACKUP"
ok "сохранено: $BACKUP"

# ---------------------------------------------------------------- 3. конфиг
say "3/4  установка reverse proxy"

echo "   --- что меняется ---"
diff -u "$BACKUP" "$DEPLOY_DIR/nginx-default.conf" || true
echo "   ---------------------"

# С этого момента любая ошибка возвращает старый конфиг на место
rollback() {
    err "СБОЙ — откатываю конфиг из бэкапа"
    cp -a "$BACKUP" "$NGINX_CONF"
    nginx -t && systemctl reload nginx && err "откат выполнен, nginx работает на старом конфиге"
}
trap rollback ERR

install -m 644 "$DEPLOY_DIR/nginx-default.conf" "$NGINX_CONF"
ok "новый конфиг записан"

say "4/4  проверка и перезагрузка nginx"
nginx -t
ok "nginx -t пройден"

systemctl reload nginx
ok "nginx перезагружен"

trap - ERR

# ---------------------------------------------------------------- итог
say "Готово"
systemctl --no-pager --lines=0 status tajscore.service | head -12
echo
echo "Бэкап конфига: $BACKUP"
echo "Откат вручную:  sudo cp -a $BACKUP $NGINX_CONF && sudo nginx -t && sudo systemctl reload nginx"
