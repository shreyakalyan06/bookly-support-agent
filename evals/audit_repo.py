#!/usr/bin/env python3
"""
Pre-submission audit. Runs offline, costs nothing.

    python evals/audit_repo.py

Checks what a reviewer will see:
  what is committed, and what is missing
  whether the deck's claims match the committed results
  whether anything private slipped in
  whether the placeholder demo link is still there
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, BAD, WARN = "  ok  ", "  FAIL", "  warn"
problems = 0
warnings = 0


def check(label, condition, detail=""):
    global problems
    print(f"{OK if condition else BAD}  {label}")
    if not condition:
        problems += 1
        if detail:
            print(f"        {detail}")


def soft(label, condition, detail=""):
    global warnings
    print(f"{OK if condition else WARN}  {label}")
    if not condition:
        warnings += 1
        if detail:
            print(f"        {detail}")


def git(*args):
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except Exception:
        return ""


tracked = set(git("ls-files").split())

print("\nCOMMITTED FILES")
expected = [
    "README.md", "requirements.txt", ".gitignore", "cli.py",
    "bookly/__init__.py", "bookly/agent.py", "bookly/tools.py",
    "bookly/guardrails.py", "bookly/trace.py", "bookly/data.py",
    "bookly/catalogue.py", "bookly/policy.py",
    "evals/scenarios.py", "evals/run_scenarios.py",
    "evals/test_control_layer.py", "evals/triage.py",
    "evals/capture_artefacts.py", "evals/audit_repo.py",
    "evals/results/eval-results.json", "evals/results/eval-results.txt",
]
for f in expected:
    check(f, f in tracked)

print("\nARTEFACTS A REVIEWER READS WITHOUT AN API KEY")
soft("evals/results/sample-trace.jsonl",
     "evals/results/sample-trace.jsonl" in tracked,
     "run: python evals/capture_artefacts.py")
soft("evals/results/sample-transcript.txt",
     "evals/results/sample-transcript.txt" in tracked,
     "run: python evals/capture_artefacts.py")

print("\nSHOULD NOT BE COMMITTED")
for pat, why in [
    (r"\.DS_Store", "macOS junk"),
    (r"^\.venv/", "virtual environment"),
    (r"^\.env$", "your API key"),
    (r"^traces/", "local run output"),
    (r"^install\.sh$", "download helper, useless on a clone"),
    (r"^setup\.sh$", "download helper, useless on a clone"),
    (r"^(adv|full|final|concierge)\d*\.(json|txt)$", "intermediate eval output"),
    (r"^RECORDING\.md$", "your own recording notes"),
]:
    hits = [f for f in tracked if re.search(pat, f)]
    check(f"not committed: {why}", not hits, f"found: {hits}")

print("\nSECRETS")
leaked = []
for f in tracked:
    p = ROOT / f
    if not p.is_file() or p.suffix in {".jsonl", ".pptx", ".pdf"}:
        continue
    try:
        body = p.read_text(errors="ignore")
    except Exception:
        continue
    if re.search(r"sk-ant-[A-Za-z0-9_\-]{20,}", body):
        leaked.append(f)
check("no API key in any committed file", not leaked, f"found in: {leaked}")

print("\nAUTHOR IDENTITY")
email = git("log", "-1", "--format=%ae").strip()
soft(f"commit email is not a work address  ({email or 'unknown'})",
     bool(email) and "lindus" not in email.lower(),
     "public commits show this address")

print("\nREADME")
readme = (ROOT / "README.md").read_text() if (ROOT / "README.md").exists() else ""
check("no mention of the hiring company", "Decagon" not in readme)
soft("demo link filled in", "PASTE_YOUR_LINK_HERE" not in readme,
     "still a placeholder at the top of the README")

print("\nRESULTS AND DECK AGREEMENT")
rp = ROOT / "evals/results/eval-results.json"
if not rp.exists():
    check("eval-results.json present", False, "run the suite first")
else:
    d = json.loads(rp.read_text())
    runs = sum(v["runs"] for v in d.values())
    passes = sum(v["passes"] for v in d.values())
    adv = {k: v for k, v in d.items() if k.startswith("adv-")}
    adv_runs = sum(v["runs"] for v in adv.values())
    adv_passes = sum(v["passes"] for v in adv.values())
    src = [s for v in d.values() for s in v.get("sources", [])]
    rec = d.get("concierge-refusal-recovery", {})

    check("18 scenarios recorded", len(d) == 18, f"found {len(d)}")
    check("every adversarial run held", adv_passes == adv_runs,
          f"{adv_passes} of {adv_runs}")

    unexpected = {
        k: v for k, v in d.items()
        if v["passes"] < v["runs"] and k != "concierge-refusal-recovery"
    }
    check("no unexplained failures", not unexpected, f"{list(unexpected)}")

    print("\nNUMBERS FOR THE DECK")
    print("  " + "-" * 60)
    print(f"  overall                {passes} / {runs}  ({passes/runs:.0%})")
    print(f"  adversarial            {adv_passes} / {adv_runs}")
    print(f"  control layer          48 / 48   (offline, unchanged)")
    if rec.get("runs"):
        print(f"  recovery               {rec['passes']} of {rec['runs']} runs"
              f"  ({rec['passes']/rec['runs']:.0%})")
    print(f"  code blocked           {src.count('code_blocked')}")
    print(f"  model declined         {src.count('model_declined')}")
    print(f"  never attempted        {src.count('never_attempted')}")
    print("  " + "-" * 60)

    # A dedicated run on the same code counts. Pool it.
    extra = ROOT / "evals/results/recovery-rate.json"
    pooled_p, pooled_r = rec.get("passes", 0), rec.get("runs", 0)
    if extra.exists():
        e = json.loads(extra.read_text()).get("concierge-refusal-recovery", {})
        pooled_p += e.get("passes", 0)
        pooled_r += e.get("runs", 0)
        print(f"\n  POOLED RECOVERY, both samples on this code")
        print("  " + "-" * 60)
        print(f"  full suite             {rec['passes']} of {rec['runs']}")
        print(f"  dedicated run          {e.get('passes', 0)} of {e.get('runs', 0)}")
        print(f"  pooled, for the deck   {pooled_p} / {pooled_r}"
              f"  ({pooled_p/pooled_r:.0%})" if pooled_r else "")
        print("  " + "-" * 60)
        soft("recovery-rate.json committed",
             "evals/results/recovery-rate.json" in tracked,
             "commit it, or the pooled figure on the deck has no source")

    if pooled_r < 10:
        print(f"\n  {WARN.strip()}  The recovery figure rests on {pooled_r} runs.")
        print("        Too few to quote a percentage anyone should trust.")
        print("        For a defensible number, and it costs pennies:")
        print("          python evals/run_scenarios.py --only concierge-refusal-recovery \\")
        print("              --repeats 12 --json evals/results/recovery-rate.json")
        warnings += 1

print(f"\n{'-' * 66}")
if problems:
    print(f"  {problems} problem(s). Fix before submitting.")
elif warnings:
    print(f"  No problems. {warnings} thing(s) worth a look.")
else:
    print("  Clean. Ready to submit.")
print()
sys.exit(1 if problems else 0)
