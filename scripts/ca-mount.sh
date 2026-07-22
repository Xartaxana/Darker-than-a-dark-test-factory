# Монтирует набор доверенных CA (/data/local/tmp/ca-store) поверх обоих каталогов
# доверия текущего mount-namespace. Вызывается install-mitm-ca.sh в namespace init;
# приложения форкаются из перезапущенного zygote и наследуют этот mount. Device sh = mksh.
#
# КРИТИЧНО: после tmpfs-mount нужно вернуть SELinux-контекст НЕ ТОЛЬКО файлам, но и
# самому каталогу-точке монтирования. Иначе точка остаётся u:object_r:tmpfs:s0,
# system_server получает отказ на листинг каталога доверия → NullPointerException
# "Attempt to get length of null array" → крэш-луп system_server при загрузке.
#
# AT-BUG-024: /apex/com.android.conscrypt (mainline-модуль conscrypt) появляется
# начиная с API 29 — на API 26/27/28 системный CA-стор ЕДИНСТВЕННЫЙ
# (/system/etc/security/cacerts), APEX-путь физически отсутствует. Гейт
# существования каталога — иначе `mount -t tmpfs` поверх несуществующего пути
# падает и (на некоторых образах) может утянуть за собой весь скрипт. Логика
# API 34 (apex-ветка) не меняется — только оборачивается условием.
STORE=/data/local/tmp/ca-store

mount -t tmpfs tmpfs /system/etc/security/cacerts
cp "$STORE"/* /system/etc/security/cacerts/
chown 0:0 /system/etc/security/cacerts/*
chmod 644 /system/etc/security/cacerts/*
chcon u:object_r:system_security_cacerts_file:s0 /system/etc/security/cacerts
chcon u:object_r:system_security_cacerts_file:s0 /system/etc/security/cacerts/*

if [ -d /apex/com.android.conscrypt/cacerts ]; then
  mount -t tmpfs tmpfs /apex/com.android.conscrypt/cacerts
  cp "$STORE"/* /apex/com.android.conscrypt/cacerts/
  chown 0:0 /apex/com.android.conscrypt/cacerts/*
  chmod 644 /apex/com.android.conscrypt/cacerts/*
  # Эталонный контекст (проверено на чистой загрузке) — тот же, что у /system-стора,
  # и для каталога, и для файлов: system_security_cacerts_file. НЕ system_file.
  chcon u:object_r:system_security_cacerts_file:s0 /apex/com.android.conscrypt/cacerts
  chcon u:object_r:system_security_cacerts_file:s0 /apex/com.android.conscrypt/cacerts/*
else
  echo "apex conscrypt store absent (API<29) - system-store mount only"
fi
