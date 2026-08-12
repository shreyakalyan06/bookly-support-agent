#!/usr/bin/env bash
#
# Bookly agent — one-time setup.
#
# Run this from the folder where you downloaded the twelve files.
# It rebuilds the package structure, creates the supporting files,
# sets up a virtual environment, and installs dependencies.
#
#   bash setup.sh
#
set -euo pipefail

echo ""
echo "Bookly agent setup"
echo "=================="

# ---------------------------------------------------------------------------
# 1. Check the downloaded files are all here
# ---------------------------------------------------------------------------
REQUIRED=(
  README.md
  agent.py catalogue.py cli.py data.py guardrails.py policy.py tools.py trace.py
  run_scenarios.py scenarios.py test_control_layer.py
)

missing=0
for f in "${REQUIRED[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "  MISSING: $f"
    missing=1
  fi
done

if [[ $missing -eq 1 ]]; then
  echo ""
  echo "Some files are missing. Download all twelve into this folder and re-run."
  exit 1
fi
echo "  all 12 files found"

# ---------------------------------------------------------------------------
# 2. Rebuild the package structure
# ---------------------------------------------------------------------------
mkdir -p bookly evals traces

mv -f agent.py catalogue.py data.py guardrails.py policy.py tools.py trace.py bookly/
mv -f run_scenarios.py scenarios.py test_control_layer.py evals/
# cli.py and README.md stay at the root

echo "  package structure rebuilt"

# ---------------------------------------------------------------------------
# 3. Supporting files
# ---------------------------------------------------------------------------
printf '"""Bookly customer support agent."""\n' > bookly/__init__.py

cat > requirements.txt <<'EOF'
anthropic>=0.40.0
EOF

cat > .gitignore <<'EOF'
.venv/
venv/
__pycache__/
*.pyc
traces/
.env
EOF

cat > .env.example <<'EOF'
ANTHROPIC_API_KEY=sk-ant-...
BOOKLY_MODEL=claude-sonnet-5
EOF

echo "  supporting files written"

# ---------------------------------------------------------------------------
# 4. Virtual environment
# ---------------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "python3 not found. Install Python 3.10 or newer, then re-run."
  exit 1
fi

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  python $PYVER"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo "  virtual environment created, dependencies installed"

# ---------------------------------------------------------------------------
# 5. Smoke test — the control layer needs no API key
# ---------------------------------------------------------------------------
echo ""
echo "Running control-layer tests (no API key needed)..."
echo ""
python evals/test_control_layer.py

cat <<'EOF'

Setup complete.

Next:

  1. Activate the environment in any new terminal:
         source .venv/bin/activate

  2. Set your API key (get one at https://console.anthropic.com):
         export ANTHROPIC_API_KEY=sk-ant-...

  3. Chat with the agent:
         python cli.py --trace

  4. Run the behavioural evaluation:
         python evals/run_scenarios.py --repeats 3

EOF
