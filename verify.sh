#!/usr/bin/env bash
#
# One command a reviewer runs. Exits non-zero on any inconsistency.
#
#   ./verify.sh          offline only, no API key needed
#   ./verify.sh --full   also runs the behavioural suite, needs a key
#
# Offline it proves three things:
#   the permission layer passes every assertion
#   the evaluation suite is capable of failing
#   the repository and its committed numbers agree
#
# With --full it regenerates the results and the captured trace first, so nothing
# downstream reads a stale figure.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

FULL=0
[[ "${1:-}" == "--full" ]] && FULL=1

FAILED=0
step() {
  printf '\n\033[1m%s\033[0m\n' "$1"
  printf '%s\n' "------------------------------------------------------------------"
}
result() {
  if [[ $1 -eq 0 ]]; then
    printf '  \033[32mpass\033[0m  %s\n' "$2"
  else
    printf '  \033[31mFAIL\033[0m  %s\n' "$2"
    FAILED=1
  fi
}

if [[ $FULL -eq 1 ]]; then
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    printf '\n  --full needs ANTHROPIC_API_KEY. Run without it for the offline checks.\n\n'
    exit 1
  fi

  step "Regenerating results. This makes real API calls."
  python evals/run_scenarios.py --repeats 3 \
    --json evals/results/eval-results.json | tee evals/results/eval-results.txt
  result $? "behavioural suite"

  step "Capturing a trace and transcript"
  python evals/capture_artefacts.py
  result $? "capture"
fi

step "1. Permission layer, offline"
python evals/test_control_layer.py | tail -3
result ${PIPESTATUS[0]} "every assertion in the permission layer"

step "2. The evaluation suite is capable of failing"
python evals/test_eval_suite.py | tail -4
result ${PIPESTATUS[0]} "stub agents are rejected by every adversarial scenario"

step "3. Repository and committed numbers agree"
python evals/audit_repo.py
result $? "audit"

printf '\n%s\n' "=================================================================="
if [[ $FAILED -eq 0 ]]; then
  printf '  \033[32mEverything agrees.\033[0m\n'
  [[ $FULL -eq 0 ]] && printf '  Run ./verify.sh --full to regenerate the numbers too.\n'
else
  printf '  \033[31mSomething disagrees. Do not submit.\033[0m\n'
fi
printf '\n'
exit $FAILED
