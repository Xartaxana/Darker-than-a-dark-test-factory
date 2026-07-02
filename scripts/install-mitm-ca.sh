#!/usr/bin/env bash
# Устанавливает CA mitmproxy в системное И APEX-хранилище доверия Android 14 (API 34).
# Требует: rootable AVD (образ default/aosp), adb root, -writable-system при старте эмулятора.
# tmpfs-mount не переживает перезагрузку — запускать после каждого рестарта эмулятора.
# Использование: bash install-mitm-ca.sh  (CA берётся из ~/.mitmproxy/mitmproxy-ca-cert.pem)
set -e
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"
ADB="${ADB:-adb}"
CA_PEM="${CA_PEM:-$USERPROFILE/.mitmproxy/mitmproxy-ca-cert.pem}"
OPENSSL="${OPENSSL:-/c/Program Files/Git/usr/bin/openssl.exe}"

HASH=$("$OPENSSL" x509 -inform PEM -subject_hash_old -in "$CA_PEM" -noout | tr -d '\r')
TMP="$(dirname "$CA_PEM")/${HASH}.0"
cp "$CA_PEM" "$TMP"
echo "CA hash = $HASH"

$ADB root >/dev/null 2>&1; sleep 2
$ADB remount >/dev/null 2>&1
$ADB push "$TMP" /system/etc/security/cacerts/ >/dev/null

$ADB shell "su 0 sh -c '
  mkdir -p /data/local/tmp/ca
  cp /system/etc/security/cacerts/* /data/local/tmp/ca/ 2>/dev/null
  mount -t tmpfs tmpfs /system/etc/security/cacerts
  cp /data/local/tmp/ca/* /system/etc/security/cacerts/
  chmod 644 /system/etc/security/cacerts/*
  chcon u:object_r:system_security_cacerts_file:s0 /system/etc/security/cacerts/* 2>/dev/null
  mount -t tmpfs tmpfs /apex/com.android.conscrypt/cacerts
  cp /data/local/tmp/ca/* /apex/com.android.conscrypt/cacerts/
  chmod 644 /apex/com.android.conscrypt/cacerts/*
  chcon u:object_r:system_file:s0 /apex/com.android.conscrypt/cacerts/* 2>/dev/null
'"
$ADB shell "ls /apex/com.android.conscrypt/cacerts/ | grep -q ${HASH} && echo 'CA installed in APEX store: OK'"
