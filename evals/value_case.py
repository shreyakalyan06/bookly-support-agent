#!/usr/bin/env python3
"""
Not part of the agent. Tooling I wrote to keep the submission honest: it checks
the repository and the deck against the committed results.

Build the value case from measured data, not from guesses.

    python evals/value_case.py

Reads two things:
  evals/results/sample-trace.jsonl   tokens and seconds per turn, from real runs
  evals/results/*.json               per-scenario timings from the eval runs

Prints the numbers for the value slide, plus the arithmetic behind each, so you
can defend any figure a reviewer questions.

Change the assumptions below to match whatever a customer tells you. They are
the only things here that are not measured.
"""

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "evals" / "results"

# ---------------------------------------------------------------------------
# ASSUMPTIONS. Not measured. Change per customer.
# ---------------------------------------------------------------------------
CONTACTS_PER_MONTH = 40_000        # a mid-size UK online retailer
COST_PER_HUMAN_CONTACT_GBP = 4.20  # loaded cost, UK, chat
CONTAINMENT = 0.60                 # share the agent finishes alone
AVG_REFUND_GBP = 22.00             # mean refund on a returned book

# Published API pricing, per million tokens. Check before quoting.
IN_PER_MTOK = 3.00
OUT_PER_MTOK = 15.00


def load_trace():
    p = RESULTS / "sample-trace.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def load_timings():
    out = []
    for f in RESULTS.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        for rec in d.values():
            if isinstance(rec, dict):
                out.extend(rec.get("seconds", []))
    return [s for s in out if isinstance(s, (int, float))]


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


turns = load_trace()
timings = load_timings()

print()
print("MEASURED")
print("-" * 68)

if turns:
    convs = {}
    for t in turns:
        c = convs.setdefault(t["conversation_id"], {"in": 0, "out": 0, "s": 0.0, "n": 0})
        c["in"] += t.get("input_tokens", 0)
        c["out"] += t.get("output_tokens", 0)
        c["s"] += t.get("seconds", 0.0)
        c["n"] += 1

    per_conv_cost = []
    for cid, c in convs.items():
        cost = c["in"] / 1e6 * IN_PER_MTOK + c["out"] / 1e6 * OUT_PER_MTOK
        per_conv_cost.append(cost)
        print(f"  conversation {cid}   {c['n']} turns   "
              f"{c['in']:,} in / {c['out']:,} out tokens   "
              f"{c['s']:.1f}s   GBP {cost:.4f}")

    mean_cost = statistics.mean(per_conv_cost)
    print()
    print(f"  cost per conversation, mean of {len(per_conv_cost)}    GBP {mean_cost:.3f}")
    print(f"  arithmetic: tokens in / 1e6 x {IN_PER_MTOK} + tokens out / 1e6 x {OUT_PER_MTOK}")
else:
    mean_cost = None
    print("  no sample-trace.jsonl yet. Run:")
    print("    python evals/capture_artefacts.py")

if timings:
    print()
    print(f"  scenario latency, {len(timings)} runs")
    print(f"    p50   {pct(timings, 50):.1f}s")
    print(f"    p95   {pct(timings, 95):.1f}s")
    print(f"    max   {max(timings):.1f}s")
    print("  a scenario is a whole conversation, so per turn is roughly half this")
else:
    print()
    print("  no timings found in evals/results/*.json")

print()
print("ASSUMED, change per customer")
print("-" * 68)
print(f"  contacts per month              {CONTACTS_PER_MONTH:,}")
print(f"  loaded cost per human contact   GBP {COST_PER_HUMAN_CONTACT_GBP:.2f}")
print(f"  containment                     {CONTAINMENT:.0%}")
print(f"  average refund                  GBP {AVG_REFUND_GBP:.2f}")

print()
print("OUTCOMES")
print("-" * 68)
contained = CONTACTS_PER_MONTH * CONTAINMENT
human_saved = contained * COST_PER_HUMAN_CONTACT_GBP
print(f"  contacts handled alone          {contained:,.0f} per month")
print(f"  human cost avoided              GBP {human_saved:,.0f} per month")

if mean_cost is not None:
    agent_cost = CONTACTS_PER_MONTH * mean_cost
    print(f"  agent inference cost            GBP {agent_cost:,.0f} per month")
    print(f"  net before licence and build    GBP {human_saved - agent_cost:,.0f} per month")
    print(f"  inference is {agent_cost / human_saved:.1%} of the cost it displaces")

print()
print("EXPOSURE, the line to lead with")
print("-" * 68)
from bookly import guardrails as g  # noqa: E402
print(f"  maximum unsupervised refund, per decision       GBP {g.AUTO_REFUND_CAP_GBP:.2f}")
print(f"  maximum unsupervised refund, per conversation   GBP "
      f"{g.AUTO_REFUND_SESSION_CAP_GBP:.2f}")
print(f"  enforced in                                    guardrails.py, outside the model")
print(f"  auditable                                      per turn, in the trace")
print()
print("  Both are constants a support manager changes. Set them to zero and every")
print("  refund routes to a person with the work already done.")
print()

sys.exit(0)
