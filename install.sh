#!/usr/bin/env bash
#
# Route downloaded project files into the right folders.
#
# Handles the browser's numbered duplicates (agent-2.py, scenarios-1.py) by
# always taking the NEWEST copy of each basename, and puts each file where it
# belongs so you cannot land agent.py in evals/ by mistake.
#
#   bash install.sh              install from ~/Downloads
#   bash install.sh ~/Desktop    install from somewhere else
#
set -euo pipefail

SRC="${1:-$HOME/Downloads}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# basename -> destination directory
declare -a MAP=(
  "agent.py:bookly"
  "catalogue.py:bookly"
  "data.py:bookly"
  "guardrails.py:bookly"
  "policy.py:bookly"
  "tools.py:bookly"
  "trace.py:bookly"
  "run_scenarios.py:evals"
  "scenarios.py:evals"
  "test_control_layer.py:evals"
  "triage.py:evals"
  "cli.py:."
  "README.md:."
)

echo ""
echo "Installing from: $SRC"
echo "Into:            $ROOT"
echo ""

mkdir -p "$ROOT/bookly" "$ROOT/evals" "$ROOT/traces"

moved=0
skipped=0

for entry in "${MAP[@]}"; do
  base="${entry%%:*}"
  dest="${entry##*:}"
  stem="${base%.*}"
  ext="${base##*.}"

  # Newest file matching stem.ext or stem-N.ext, by modification time.
  # Collected into an array first: piping find straight into `xargs ls -t`
  # silently lists the CURRENT directory when find matches nothing, which
  # picked up random entries instead of skipping cleanly.
  candidates=()
  while IFS= read -r f; do
    [[ -n "$f" ]] && candidates+=("$f")
  done < <(find "$SRC" -maxdepth 1 -type f \
             \( -name "$base" -o -name "$stem-[0-9].$ext" -o -name "$stem-[0-9][0-9].$ext" \) \
             2>/dev/null)

  if [[ ${#candidates[@]} -eq 0 ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  newest="${candidates[0]}"
  for f in "${candidates[@]}"; do
    [[ "$f" -nt "$newest" ]] && newest="$f"
  done

  if [[ -z "$newest" ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  target="$ROOT/$dest/$base"
  cp "$newest" "$target"
  echo "  $(basename "$newest")  ->  $dest/$base"
  rm -f "$newest"
  moved=$((moved + 1))
done

echo ""
echo "  $moved installed, $skipped not present in $SRC"

# Make sure the package marker survives
[[ -f "$ROOT/bookly/__init__.py" ]] || printf '"""Bookly customer support agent."""\n' > "$ROOT/bookly/__init__.py"

echo ""
echo "Verifying..."
echo ""

cd "$ROOT"

if python -c "import ast,pathlib,sys
bad=0
for p in pathlib.Path('.').rglob('*.py'):
    if '.venv' in str(p): continue
    try: ast.parse(p.read_text())
    except SyntaxError as e: print(f'  SYNTAX ERROR {p}: {e}'); bad=1
sys.exit(bad)"; then
  echo "  all python files parse"
else
  echo "  a file is broken -- re-download it"
  exit 1
fi

python evals/test_control_layer.py | tail -2

echo ""
echo "Files now in place:"
ls bookly/*.py | sed 's/^/  /'
ls evals/*.py | sed 's/^/  /'
echo ""
