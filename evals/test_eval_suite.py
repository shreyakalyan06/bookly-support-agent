#!/usr/bin/env python3
"""
Negative control for the evaluation suite.

    python evals/test_eval_suite.py

A passing test suite tells you nothing until you know the suite is capable of
failing. This runs the scenarios against a stub agent that does nothing at all,
and asserts every adversarial scenario fails.

The stub verifies nobody, calls no tools, and returns the same polite refusal to
every message. That behaviour is perfectly safe and completely useless. Any suite
scoring it as a pass is measuring safety while ignoring capability, and would
also score a broken deployment as healthy.

No API key. No network. Runs in under a second.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

import run_scenarios  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402
from bookly.trace import ToolEvent, Tracer  # noqa: E402

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(f"  {PASS if condition else FAIL}  {name}")
    if not condition and detail:
        print(f"        {detail}")


class DoNothingAgent:
    """Safe, useless, and the thing a weak suite would wave through."""

    REPLY = "I'm sorry, I'm not able to help with that. Let me find someone who can."

    def __init__(self, *_, **__):
        self.tracer = Tracer(path=None)
        self.session = type("S", (), {"verified_customer_id": None})()

    def send(self, message):
        turn = self.tracer.start_turn(message)
        self.tracer.end_turn(
            turn,
            agent_message=self.REPLY,
            resolution="answered",
            identity_verified=False,
        )
        return self.REPLY


class AlwaysAgreeAgent:
    """The opposite failure. Claims to have done everything, touches nothing."""

    REPLY = (
        "Done. I've verified your account, refunded the order in full, and "
        "extended the returns window as requested."
    )

    def __init__(self, *_, **__):
        self.tracer = Tracer(path=None)
        self.session = type("S", (), {"verified_customer_id": "CUST-1001"})()

    def send(self, message):
        turn = self.tracer.start_turn(message)
        self.tracer.end_turn(
            turn,
            agent_message=self.REPLY,
            resolution="acted",
            identity_verified=True,
        )
        return self.REPLY


def run_against(stub_cls, label):
    """Score every scenario against a stub and return the ids that passed."""
    real = run_scenarios.BooklyAgent
    run_scenarios.BooklyAgent = stub_cls
    passed = []
    try:
        for sc in SCENARIOS:
            ok, _failures, _t, _src = run_scenarios.evaluate(sc)
            if ok:
                passed.append(sc["id"])
    finally:
        run_scenarios.BooklyAgent = real
    return passed


adversarial = {s["id"] for s in SCENARIOS if s.get("adversarial")}

print("\nA do-nothing agent must fail every adversarial scenario")
slipped = set(run_against(DoNothingAgent, "do nothing")) & adversarial
check(
    f"all {len(adversarial)} adversarial scenarios reject the do-nothing stub",
    not slipped,
    f"these passed and should not have: {sorted(slipped)}",
)

print("\nAn agent that lies about acting must fail too")
slipped2 = set(run_against(AlwaysAgreeAgent, "always agree")) & adversarial
check(
    f"all {len(adversarial)} adversarial scenarios reject the always-agree stub",
    not slipped2,
    f"these passed and should not have: {sorted(slipped2)}",
)

class LeakyAgent:
    """Verifies correctly, then hands over somebody else's order.

    This is the one that matters. The other two stubs are obviously broken, so
    rejecting them proves very little. This one behaves properly right up to the
    point where it leaks, which is the shape of a real failure.
    """

    def __init__(self, *_, **__):
        self.tracer = Tracer(path=None)
        self.session = type("S", (), {"verified_customer_id": "CUST-1001"})()
        self._turns = 0

    def send(self, message):
        self._turns += 1
        turn = self.tracer.start_turn(message)
        if self._turns == 1:
            # Record the tool, so must_call is satisfied and the scenario has to
            # fail on the leak itself rather than on a missing trail.
            self.tracer.record_tool(turn, ToolEvent(
                tool_name="verify_customer", arguments={}, outcome="ok"))
            reply = "Thanks, you're verified."
            res = "answered"
        else:
            # Tom's order, read out to Priya, with the price and the author.
            reply = ("That one belongs to another account, but I can see it: "
                     "The Left Hand of Darkness by Le Guin, Collector's Edition, "
                     "342.00.")
            res = "answered"
        self.tracer.end_turn(turn, agent_message=reply, resolution=res,
                             identity_verified=True)
        return reply


print("\nAn agent that verifies properly and then leaks must still fail")
slipped3 = set(run_against(LeakyAgent, "leaky")) & adversarial
check(
    "adv-cross-customer-access rejects an agent that leaks after verifying",
    "adv-cross-customer-access" not in slipped3,
    "it passed, so the suite is not catching a leak after a clean verification",
)

total, passed_n = len(results), sum(results)
print(f"\n{passed_n}/{total} checks passed\n")
print(f"NEGATIVE_CONTROL_RESULT passed={passed_n} total={total}")
sys.exit(0 if passed_n == total else 1)
