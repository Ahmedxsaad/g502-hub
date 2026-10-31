#!/usr/bin/env bash
# Update and compile Qt translations for G502 Hub
set -euo pipefail

cd "$(dirname "$0")/.."

LUPDATE=$(which pyside6-lupdate || which lupdate-qt6 || which /usr/lib/qt6/bin/lupdate || which lupdate)
LRELEASE=$(which pyside6-lrelease || which lrelease-qt6 || which /usr/lib/qt6/bin/lrelease || which lrelease)

echo "Using lupdate: $LUPDATE"
echo "Using lrelease: $LRELEASE"

mkdir -p g502hub/gui/translations

echo "Updating translation source files (.ts)..."
"$LUPDATE" -extensions py g502hub/ -ts g502hub/gui/translations/zh_CN.ts

echo "Compiling binary translation files (.qm)..."
for ts in g502hub/gui/translations/*.ts; do
    qm="${ts%.ts}.qm"
    echo "  $ts -> $qm"
    "$LRELEASE" "$ts" -qm "$qm"
done

echo "Translations successfully updated!"
