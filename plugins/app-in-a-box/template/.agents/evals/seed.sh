#!/usr/bin/env bash
# Seed an eval run's empty workspace with this project, so a skill that reads the
# repo (feature-discovery, backlog) is graded on a real app instead of an empty folder.
# Called from a case's setup.sh (case.yaml `context.scaffold_script`); the runner
# starts it in the workspace and only runs it under `claude plugin eval --scaffold`.
#   In a generated app: copies the tracked files (`git ls-files`, so no node_modules
#   or secrets in .env).
#   In the App in a Box kit (this file sits under template/): renders the template.
# Then adds the fixture brief if the project has none, and makes one commit.
set -euo pipefail
evals="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$evals/../.." && pwd)"
if [ -f "$root/../scripts/render.py" ] && [ -f "$root/../.claude-plugin/plugin.json" ]; then
  python3 "$root/../scripts/render.py" --target "$PWD" --name "Streak Club" --slug streak-club \
    --bundle-id com.example.streakclub --owner example --one-liner "Keep one small habit going" --force >/dev/null
else
  (cd "$root" && git ls-files -z | tar --null -T - -cf -) | tar -xf -
fi
[ -f docs/product/BRIEF.md ] || { mkdir -p docs/product; cp "$evals/fixtures/BRIEF.md" docs/product/BRIEF.md; }
git init -q -b main
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "seed" --no-gpg-sign
