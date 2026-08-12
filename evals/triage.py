#!/usr/bin/env python3
"""
Failure triage.

Reads results.json from a previous run and groups failures by cause, so you can
tell whether the agent misbehaved or the assertion was wrong. Costs nothing, since
it re-reads what you already paid for.

    python evals/triage.py results.json

Three kinds:

  agent bug      the agent did something a customer would object to
  eval bug       the agent did something reasonable and the test called it wrong
  underspecified the script gave the agent no room to do the thing

Only the first gets fixed in the agent. The second gets fixed in the test, on the
record. The third is a scenario design problem.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

data = json.loads(Path(sys.argv[1]).read_text())

print("\nPer scenario")
print("-" * 72)

by_kind = defaultdict(list)

for scenario_id, rec in sorted(data.items(), key=lambda kv: kv[1]["passes"] / max(kv[1]["runs"], 1)):
    rate = rec["passes"] / max(rec["runs"], 1)
    flag = "ok  " if rate == 1.0 else ("warn" if rate >= 0.5 else "FAIL")
    print(f"\n  [{flag}] {scenario_id}  {rec['passes']}/{rec['runs']} ({rate:.0%})")

    if not rec["failures"]:
        continue

    for reason, count in Counter(rec["failures"]).most_common():
        print(f"          {count}x  {reason}")

        # Classify the failure by its shape
        if "expected a call to" in reason:
            kind = "agent did not use a tool the test required"
        elif "should not have called" in reason:
            kind = "agent used a tool the test forbade"
        elif "succeeded and should not have" in reason:
            kind = "GUARDRAIL BREACH -- investigate first"
        elif "expected one of these guardrails" in reason:
            kind = "expected refusal did not happen"
        elif "final resolution was" in reason:
            kind = "resolution classification mismatch"
        elif "without offering the customer anywhere to go" in reason:
            kind = "recovery not offered"
        elif "citation" in reason:
            kind = "citation mismatch"
        else:
            kind = "other"

        by_kind[kind].append((scenario_id, count))

print("\n\nFailures grouped by cause")
print("-" * 72)
for kind, items in sorted(by_kind.items(), key=lambda kv: -sum(c for _, c in kv[1])):
    total = sum(c for _, c in items)
    print(f"\n  {total:>3}  {kind}")
    for scenario_id, count in items:
        print(f"       {count}x  {scenario_id}")

print("\n\nWhere to look first")
print("-" * 72)
print("""
  1. Any "GUARDRAIL BREACH" line. That is a real defect and nothing else
     matters until it is explained.

  2. "resolution classification mismatch" is usually MY bug, not the agent's.
     The classifier decides "clarifying" by checking whether the reply ends in
     a question mark, which is a bad heuristic -- an agent that asks a question
     and then adds a closing line gets misfiled.

  3. "agent used a tool the test forbade" -- read the transcript before
     believing the test. Calling get_order on both of a customer's orders to
     summarise them is arguably better service than the test allows.

  4. "recovery not offered" on a single-turn scenario is probably
     underspecified. The agent may reasonably refuse first and offer an
     alternative when the customer responds -- but the script never gives it a
     second turn.

  Re-run individual scenarios with transcripts before changing anything:

      python evals/run_scenarios.py --only concierge-refusal-recovery --verbose
""")
