#!/usr/bin/env python3
"""
Tests for the permission checks.

No API key, no network, under a second. That is the point. The rules that must
never fail are ordinary Python, so they get tested like ordinary Python: give them
a situation, assert the answer, same result every time.

The model's behaviour needs a different kind of testing, because it does not reply
identically twice. That lives in run_scenarios.py.

    python evals/test_control_layer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bookly import catalogue, data, guardrails, policy, tools  # noqa: E402
from bookly.guardrails import Session  # noqa: E402

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(f"  {PASS if condition else FAIL}  {name}")
    if not condition and detail:
        print(f"        {detail}")


def verified():
    data.reset_state()
    s = Session()
    tools.verify_customer(s, email="priya.raman@example.com", postcode="SW1A 1AA")
    return s


print("\nNothing reachable before verification")
s = Session()
for tool, fn in (("find_orders", tools.find_orders),
                 ("get_order", lambda x: tools.get_order(x, order_id="ORD-84201")),
                 ("initiate_return", lambda x: tools.initiate_return(
                     x, order_id="ORD-84201", item_id="ITM-1", reason="x"))):
    payload, _, _ = fn(s)
    check(f"{tool} refused", payload.get("refused") is True, payload)

print("\nVerification")
s = Session()
payload, _, _ = tools.verify_customer(s, email="priya.raman@example.com", postcode="nope")
check("wrong postcode rejected", payload.get("verified") is False)
payload, _, _ = tools.verify_customer(s, email="priya.raman@example.com", postcode="sw1a1aa")
check("correct credentials accepted, spacing and case ignored", payload.get("verified") is True)
check("session now carries the identity", s.verified_customer_id == "CUST-1001")

s2 = Session()
for _ in range(3):
    tools.verify_customer(s2, email="priya.raman@example.com", postcode="nope")
payload, _, _ = tools.verify_customer(s2, email="priya.raman@example.com", postcode="SW1A 1AA")
check("three failures lock that session out", payload.get("refused") is True)
fresh, _, _ = tools.verify_customer(
    Session(), email="priya.raman@example.com", postcode="SW1A 1AA")
check("but a different session is unaffected, so nobody can lock an account",
      fresh.get("verified") is True, fresh)

print("\nOne customer cannot read another's order")
s = verified()
payload, dec, _ = tools.get_order(s, order_id="ORD-84420")
check("refused", payload.get("ok") is False)
check("the wording does not confirm the order exists",
      "no order found" in payload["reason"].lower() and "belong" not in payload["reason"].lower(),
      payload["reason"])
check("the guardrail says the same thing as the tool",
      payload["reason"] == dec["reason"], f"{payload['reason']!r} vs {dec['reason']!r}")

print("\nEvery failed return looks identical")
s = verified()
bogus_item, _, _ = tools.initiate_return(s, order_id="ORD-84201", item_id="ITM-99", reason="x")
other_cust, _, _ = tools.initiate_return(s, order_id="ORD-84420", item_id="ITM-1", reason="x")
no_order, _, _ = tools.initiate_return(s, order_id="ORD-00000", item_id="ITM-1", reason="x")
check("bogus item and another customer's order are byte-identical",
      bogus_item == other_cust, f"{bogus_item} vs {other_cust}")
check("a nonexistent order matches both", no_order == bogus_item)
check("no reference or item id leaks into the wording",
      "ORD-" not in bogus_item["reason"] and "ITM-" not in bogus_item["reason"])

print("\nReturn eligibility comes from dates, not from the conversation")
s = verified()
for order_id, expected in (("ORD-84201", "return.eligible"),
                           ("ORD-84315", "return.not_delivered"),
                           ("ORD-79930", "return.window_expired")):
    payload, _, _ = tools.get_order(s, order_id=order_id)
    rule = payload["return_eligibility"]["rule"]
    check(f"{order_id} gives {expected}", rule == expected, rule)

no_date = {"status": "delivered", "delivered_date": None, "return_status": None}
check("delivered with no date refuses rather than crashing",
      guardrails.check_returnable(no_date).rule == "return.no_delivery_date")

print("\nThe refund cap checks the amount, not the order total")
big = {"currency": "GBP", "total_pence": 12_000,
       "items": [{"item_id": "ITM-1", "price_pence": 2_000}]}
check("2000p from a 12000p order is allowed",
      guardrails.check_refund_value(big, pence=2_000).permitted is True)
check("with no amount it falls back to the total and blocks",
      guardrails.check_refund_value(big).permitted is False)
# ORD-84420 is Tom's, so verify as Tom rather than Priya.
data.reset_state()
s = Session()
tools.verify_customer(s, email="tom.whitfield@example.com", postcode="M1 4BT")
payload, _, _ = tools.initiate_return(s, order_id="ORD-84420", item_id="ITM-1", reason="x")
check("a £342 item needs a person", payload.get("rule") == "refund.above_auto_cap", payload)
check("and the model is told a colleague can still do it",
      payload.get("next_step") == "escalate_to_human")

print("\nReturns are per item, not per order")
s = verified()
first, _, _ = tools.initiate_return(s, order_id="ORD-84201", item_id="ITM-2", reason="dup")
check("the first book goes back", first.get("ok") is True, first)
check("the amount is the item price in pence, not the order total",
      first.get("refund_pence") == 1499, first.get("refund_pence"))
second, _, _ = tools.initiate_return(s, order_id="ORD-84201", item_id="ITM-1", reason="also")
check("the other book from the same order also goes back",
      second.get("ok") is True, second)
again, _, _ = tools.initiate_return(s, order_id="ORD-84201", item_id="ITM-1", reason="again")
check("but the same item twice is blocked",
      again.get("rule") == "return.already_in_progress", again)

print("\nreset_state fully isolates the fixtures")
data.reset_state()
live, fixture = data.ORDERS["ORD-84201"], data._ORDER_FIXTURES["ORD-84201"]
aliased = [k for k in live
           if isinstance(live[k], (list, dict, set)) and live[k] is fixture.get(k)]
check("no mutable field is shared with the fixture", not aliased, aliased)
s = verified()
tools.initiate_return(s, order_id="ORD-84201", item_id="ITM-1", reason="x")
check("a completed return does not leak into the fixture",
      fixture.get("returned_item_ids") == [], fixture.get("returned_item_ids"))
data.reset_state()
s = verified()
repeat, _, _ = tools.initiate_return(s, order_id="ORD-84201", item_id="ITM-1", reason="x")
check("so the same scenario passes twice in a row", repeat.get("ok") is True, repeat)

print("\nDispatch fails closed")
check("a tool with no policy entry is refused",
      guardrails.check_dispatch(Session(), "drop_everything").rule == "dispatch.unknown_tool")
check("every handler has a tier",
      not set(tools.HANDLERS) - set(guardrails.ACTION_TIERS),
      sorted(set(tools.HANDLERS) - set(guardrails.ACTION_TIERS)))
check("every tier entry has a handler",
      not set(guardrails.ACTION_TIERS) - set(tools.HANDLERS),
      sorted(set(guardrails.ACTION_TIERS) - set(tools.HANDLERS)))
check("every check name a tier asks for actually exists",
      all(n in {"identity", "not_escalated"}
          for names in guardrails.TIER_CHECKS.values() for n in names),
      guardrails.TIER_CHECKS)
check("refunds stop once the conversation goes to a person",
      guardrails.check_dispatch(
          Session(verified_customer_id="CUST-1001", escalated=True),
          "initiate_return").rule == "dispatch.already_escalated")
check("an unknown tool is treated as the strictest tier",
      guardrails.tier_of("drop_everything") == 2)

print("\nPolicy answers are grounded, or absent")
check("a returns question finds the returns passage",
      any(h["passage_id"] == "POL-RET-01" for h in policy.search_policy(
          "how long do I have to return a book")))
check("an out-of-scope question finds nothing",
      policy.search_policy("do you sell audiobooks on vinyl") == [])
check("a long rambling out-of-scope question also finds nothing",
      policy.search_policy(
          "I have been a customer for years and buy a lot of books, mostly fantasy "
          "and some literary fiction, and I wondered whether you run a loyalty "
          "points scheme where what I spend earns me credit on future orders") == [],
      "length alone used to drag an irrelevant passage over the cutoff")
payload, _, _ = tools.search_policy(Session(), query="do you sell audiobooks on vinyl")
check("and the model is told to hand over rather than improvise",
      payload.get("found") is False and "human" in payload["instruction"])

print("\nRecommendations are open but grounded")
s = Session()
payload, _, _ = tools.recommend_books(s, liked_title="Piranesi")
check("no verification needed", payload.get("found") is True, payload)
titles = {r["title"] for r in payload["recommendations"]}
check("every suggestion is a real, in-stock book",
      all(catalogue.find_by_title(t) and catalogue.find_by_title(t)["in_stock"] for t in titles),
      titles)
check("every suggestion carries a reason",
      all(r.get("why") for r in payload["recommendations"]))
payload, _, _ = tools.recommend_books(s, liked_title="Dune")
check("a book we do not stock returns nothing rather than a guess",
      payload.get("found") is False)

total, passed = len(results), sum(results)
print(f"\n{passed}/{total} checks passed\n")
sys.exit(0 if passed == total else 1)
