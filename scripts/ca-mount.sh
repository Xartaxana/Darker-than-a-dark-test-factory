# Монтирует набор доверенных CA (/data/local/tmp/ca-store) поверх обоих каталогов
# доверия текущего mount-namespace. Вызывается install-mitm-ca.sh в namespace init;
# приложения форкаются из перезапущенного zygote и наследуют этот mount. Device sh = mksh.
#
# КРИТИЧНО: после tmpfs-mount нужно вернуть SELinux-контекст НЕ ТОЛЬКО файлам, но и
# самому каталогу-точке монтирования. Иначе точка остаётся u:object_r:tmpfs:s0,
# system_server получает отказ на листинг каталога доверия → NullPointerException
# "Attempt to get length of null array" → крэш-луп system_server при загрузке.
STORE=/data/local/tmp/ca-store

mount -t tmpfs tmpfs /system/etc/security/cacerts
cp "$STORE"/* /system/etc/security/cacerts/
chown 0:0 /system/etc/security/cacerts/*
chmod 644 /system/etc/security/cacerts/*
chcon u:object_r:system_security_cacerts_file:s0 /system/etc/security/cacerts
chcon u:object_r:system_security_cacerts_file:s0 /system/etc/security/cacerts/*

mount -t tmpfs tmpfs /apex/com.android.conscrypt/cacerts
cp "$STORE"/* /apex/com.android.conscrypt/cacerts/
chown 0:0 /apex/com.android.conscrypt/cacerts/*
chmod 644 /apex/com.android.conscrypt/cacerts/*
# Эталонный контекст (проверено на чистой загрузке) — тот же, что у /system-стора,
# и для каталога, и для файлов: system_security_cacerts_file. НЕ system_file.
chcon u:object_r:system_security_cacerts_file:s0 /apex/com.android.conscrypt/cacerts
chcon u:object_r:system_security_cacerts_file:s0 /apex/com.android.conscrypt/cacerts/*
