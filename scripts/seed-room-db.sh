#!/usr/bin/env bash
# Сидинг/снятие состояния Room-БД приложения через run-as (работает на debug-сборке).
# ВАЖНО: Room в режиме WAL держит свежие данные в *.db-wal и *.db-shm — тянуть/класть
# нужно все три файла вместе, иначе прочитаешь пустую схему.
#
#   bash seed-room-db.sh pull  <dest_dir>   # снять текущее состояние (3 файла)
#   bash seed-room-db.sh push  <src_dir>    # залить состояние (перед стартом приложения)
set -e
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"
ADB="${ADB:-adb}"; PKG="com.example.ao3_wrapper"; DB="ao3_ratings.db"
FILES="$DB $DB-wal $DB-shm"
CMD="$1"; DIR="$2"

$ADB shell am force-stop $PKG; sleep 1
case "$CMD" in
  pull)
    mkdir -p "$DIR"
    for f in $FILES; do
      $ADB exec-out run-as $PKG cat "databases/$f" > "$DIR/$f" 2>/dev/null || true
    done
    echo "pulled -> $DIR"; ls -l "$DIR" ;;
  push)
    for f in $FILES; do
      [ -f "$DIR/$f" ] || continue
      $ADB push "$DIR/$f" /data/local/tmp/ >/dev/null
      $ADB shell "run-as $PKG cp /data/local/tmp/$f databases/$f"
    done
    echo "seeded from $DIR (start app now)" ;;
  *) echo "usage: seed-room-db.sh pull|push <dir>"; exit 1 ;;
esac
