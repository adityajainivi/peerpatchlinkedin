#!/bin/bash
# Mac: double-click this file. Mac or Linux terminal: bash run.command
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.9 or newer is needed. Get it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close."
  exit 1
fi

if [ ! -f .venv/.installed ]; then
  echo "First run: setting things up. This takes about a minute."
  rm -rf .venv
  if ! "$PY" -m venv .venv || ! .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt; then
    rm -rf .venv
    echo "Setup failed. Check your internet connection and run this again."
    read -r -p "Press Enter to close."
    exit 1
  fi
  touch .venv/.installed
fi

.venv/bin/python -m peerpatch_linkedin "$@"
status=$?
if [ $# -eq 0 ] && [ -t 0 ]; then
  read -r -p "Press Enter to close."
fi
exit $status
