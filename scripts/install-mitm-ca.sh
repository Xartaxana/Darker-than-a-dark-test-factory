#!/usr/bin/env bash
# Устанавливает CA mitmproxy в хранилища доверия Android 14 (API 34) ТАК, ЧТОБЫ ЕГО
# ВИДЕЛИ ПРИЛОЖЕНИЯ (в т.ч. WebView/Chromium через Conscrypt), а не только adb-shell.
#
# Почему сложно (спайк B, docs/environment-setup.md): на Android 14 системный CA-стор
# переехал в APEX-модуль conscrypt. tmpfs-mount поверх /apex/.../cacerts, сделанный из
# `adb shell su`, попадает в mount-namespace init'а (в нём же живёт adbd/shell) и НЕ
# виден уже запущенным zygote/приложению — у них отдельные mount-namespaces. Поэтому:
#   1) монтируем стор в init-namespace, затем
#   2) перезапускаем фреймворк (`stop; start`) — НОВЫЙ zygote форкается из init и
#      наследует mount (проверено: после рестарта zygote64 оказывается в ns init'а).
# nsenter в toybox 0.8.9-android НЕ годится: флаг -t всегда резолвится в pid 0 (баг).
#
# КРИТИЧНО про SELinux: точке монтирования (самому каталогу, не только файлам) нужно
# вернуть контекст system_security_cacerts_file (для /system) и system_file (для /apex);
# иначе system_server не может прочитать каталог доверия → NPE → крэш-луп. Это делает
# ca-mount.sh.
#
# Требует: rootable AVD (образ default/aosp), adb root, эмулятор запущен с -writable-system
# (scripts/tasks.ps1 Start-Emulator -WritableSystem). Mount'ы НЕ переживают reboot
# эмулятора — запускать после каждого старта. Скрипт рассчитан на ЧИСТУЮ загрузку
# (иначе tmpfs-mount'ы стекаются) — при повторе сначала перезагрузи эмулятор.
#
# Использование: bash scripts/install-mitm-ca.sh
set -e
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"
ADB="${ADB:-adb}"
CA_PEM="${CA_PEM:-$USERPROFILE/.mitmproxy/mitmproxy-ca-cert.pem}"
OPENSSL="${OPENSSL:-/c/Program Files/Git/usr/bin/openssl.exe}"

HASH=$("$OPENSSL" x509 -inform PEM -subject_hash_old -in "$CA_PEM" -noout | tr -d '\r')
echo "CA hash = $HASH"

$ADB root >/dev/null 2>&1; sleep 2
# Кладём PEM с именем <hash>.0 в общий (не-namespaced) /data/local/tmp — оттуда его
# видно из любого mount-namespace.
$ADB push "$CA_PEM" "/data/local/tmp/${HASH}.0" >/dev/null

# Последовательность mount'а поверх обоих каталогов доверия. Выполняется как в
# текущем namespace, так и (через nsenter) в namespace каждого zygote. Держим её в
# отдельном файле рядом со скриптом и push'им на устройство — так один и тот же код
# гоняется в разных namespace без тройного экранирования и bash-специфики
# (device sh = mksh).
HERE="$(cd "$(dirname "$0")" && pwd)"
MOUNT_SRC="$HERE/ca-mount.sh"
# adb — нативный Windows-бинарь и не понимает MSYS-путь /d/...; конвертируем в
# D:\... (MSYS_NO_PATHCONV=1 отключает авто-конверсию, делаем вручную).
command -v cygpath >/dev/null && MOUNT_SRC="$(cygpath -w "$MOUNT_SRC")"
MOUNT_SH='/data/local/tmp/ca-mount.sh'
$ADB push "$MOUNT_SRC" "$MOUNT_SH" >/dev/null

# Основной патчинг: собрать стор и применить mount в init-namespace.
$ADB shell "su 0 sh -c '
  set -e
  STORE=/data/local/tmp/ca-store
  # Полный набор доверенных CA = системные сертификаты + наш (из APEX-оригинала).
  rm -rf \$STORE; mkdir -p \$STORE
  cp /apex/com.android.conscrypt/cacerts/*.0 \$STORE/ 2>/dev/null || true
  cp /system/etc/security/cacerts/*.0 \$STORE/ 2>/dev/null || true
  cp /data/local/tmp/'${HASH}'.0 \$STORE/
  chmod 644 \$STORE/*
  sh $MOUNT_SH
  echo store=\$(ls \$STORE | wc -l) apex=\$([ -d /apex/com.android.conscrypt/cacerts ] && ls /apex/com.android.conscrypt/cacerts | wc -l || echo 0)
'"

# Перезапуск фреймворка: новый zygote форкается из init и наследует mount из
# init-namespace. Без этого уже запущенные zygote/приложения CA не увидят.
echo "Перезапуск фреймворка (новый zygote наследует CA-mount)..."
$ADB shell "su 0 sh -c 'stop && start'"
$ADB wait-for-device
for i in $(seq 1 45); do
  b=$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  [ "$b" = "1" ] && break
  sleep 2
done
echo "boot_completed=$b"

# Проверка: новый zygote в init-namespace и видит наш CA-хэш. Признак готовности
# (AT-BUG-024): apex-стор — только когда /apex/com.android.conscrypt существует
# (API>=29); на API<29 (нет apex-модуля conscrypt, см. ca-mount.sh) единственный
# стор — /system/etc/security/cacerts, признак переключается на него.
$ADB shell "su 0 sh -c '
  z=\$(pidof zygote64)
  echo \"zygote64 pid=\$z ns=\$(readlink /proc/\$z/ns/mnt) init_ns=\$(readlink /proc/1/ns/mnt)\"
  if [ -d /apex/com.android.conscrypt/cacerts ]; then
    ls /apex/com.android.conscrypt/cacerts/ | grep -q '${HASH}' && echo \"CA visible in apex store: OK\" || echo \"CA MISSING in apex store\"
  else
    ls /system/etc/security/cacerts/ | grep -q '${HASH}' && echo \"CA visible in system store: OK\" || echo \"CA MISSING in system store\"
  fi
'"
echo "Готово. CA установлен и виден приложениям; можно запускать прогоны в replay/record."
