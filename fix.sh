#!/usr/bin/env bash
#
# Clears the five problems the audit reported. Run from the repo root.
#
#   bash fix.sh
#
set -euo pipefail

echo ""
echo "1. Removing the download helpers. They only worked for pasting files out of"
echo "   a chat, and they fail on a clone."
git rm -f --quiet install.sh setup.sh 2>/dev/null || true
rm -f install.sh setup.sh
echo "   done"

echo ""
echo "2. Keeping RECORDING.md local. Those are notes to yourself, including lines"
echo "   to say out loud. A reviewer reading them learns nothing about the agent."
git rm --cached --quiet RECORDING.md 2>/dev/null || true
grep -q "RECORDING.md" .gitignore || printf '\n# Notes to myself, not a deliverable\nRECORDING.md\n' >> .gitignore
echo "   done"

echo ""
echo "3. Tracking the two new scripts."
git add evals/capture_artefacts.py evals/audit_repo.py .gitignore
echo "   done"

echo ""
echo "4. Committing the dedicated recovery run, so the pooled figure on the deck"
echo "   has a source a reviewer can open."
if [[ -f evals/results/recovery-rate.json ]]; then
  git add evals/results/recovery-rate.json
  echo "   done"
else
  echo "   recovery-rate.json not found. Run:"
  echo "     python evals/run_scenarios.py --only concierge-refusal-recovery \\"
  echo "         --repeats 12 --json evals/results/recovery-rate.json"
fi

echo ""
echo "5. Capturing the trace and transcript. These need your API key."
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  python evals/capture_artefacts.py || true
  git add evals/results/sample-trace.jsonl evals/results/sample-transcript.txt 2>/dev/null || true
  echo "   done"
else
  echo "   ANTHROPIC_API_KEY is not set in this shell. Run:"
  echo "     export ANTHROPIC_API_KEY=sk-ant-..."
  echo "     python evals/capture_artefacts.py"
  echo "     git add evals/results/"
fi

echo ""
echo "Now audit again:"
echo "  python evals/audit_repo.py"
echo ""
echo "Then, when it exits clean:"
echo "  git add -A"
echo "  git commit -m \"Add capture and audit tooling, commit pooled recovery run\""
echo "  git push"
echo ""
