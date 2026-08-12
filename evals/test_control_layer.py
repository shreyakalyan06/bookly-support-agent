#!/usr/bin/env python3
"""
Tests for the control layer.

These run with no API key and no network. That is the point: the parts of this
system that must never fail are deterministic, so they can be tested the way
ordinary software is tested. Only the language part needs the softer,
distributional evaluation in run_scenarios.py.

Being able to draw that line -- this half gets unit tests, that half gets
statistical evaluation -- is the practical payoff of the architecture.

    python evals/test_control_layer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bookly import catalogue, data, guardrails, policy, tools  # noqa: E402
from bookly.guardrails import Session  # noqa: E402

data.reset_state()  # start from pristine fixtures regardless of run order

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(f"  {PASS if condition else FAIL}  {name}")
    if not condition and detail:
        print(f"        {detail}")


print("\nIdentity gate")
s = Session()
payload, gate, _ = tools.find_orders(s)
check("order list refused before verification", payload.get("refused") is True, payload)
payload, gate, _ = tools.get_order(s, order_id="ORD-84201")
check("order detail refused before verification", payload.get("refused") is True, payload)
payload, gate, _ = tools.initiate_return(s, order_id="ORD-84201", item_id="ITM-1", reason="test")
check("return refused before verification", payload.get("refused") is True, payload)

print("\nVerification")
s = Session()
payload, _, _ = tools.verify_customer(s, email="priya.raman@example.com", postcode="wrong")
check("wrong postcode rejected", payload.get("verified") is False)
check("attempt counted", s.verification_attempts == 1)
payload, _, _ = tools.verify_customer(s, email="priya.raman@example.com", postcode="sw1a1aa")
check("correct credentials accepted, whitespace/case insensitive", payload.get("verified") is True)
check("session now carries identity", s.verified_customer_id == "CUST-1001")

s2 = Session()
for _ in range(3):
    tools.verify_customer(s2, email="priya.raman@example.com", postcode="nope")
payload, _, _ = tools.verify_customer(s2, email="priya.raman@example.com", postcode="SW1A 1AA")
check("attempt limit blocks even a correct guess afterwards", payload.get("refused") is True)

print("\nOwnership isolation")
payload, _, _ = tools.get_order(s, order_id="ORD-84420")  # belongs to CUST-1002
check("cannot read another customer's order", payload.get("ok") is False)
check(
    "refusal does not confirm the order exists",
    "does not belong" not in str(payload).lower() and "no order found" in str(payload).lower(),
    payload,
)

print("\nReturn eligibility")
payload, _, _ = tools.get_order(s, order_id="ORD-84201")
check("recent delivered order is returnable", payload["return_eligibility"]["returnable"] is True)
payload, _, _ = tools.get_order(s, order_id="ORD-84315")
check("in-transit order is not returnable", payload["return_eligibility"]["returnable"] is False)
check("reason is 'not delivered', not 'window expired'",
      payload["return_eligibility"]["rule"] == "return.not_delivered",
      payload["return_eligibility"])
payload, _, _ = tools.get_order(s, order_id="ORD-79930")
check("104-day-old order is outside the window",
      payload["return_eligibility"]["rule"] == "return.window_expired")

print("\nValue ceiling")
s3 = Session()
tools.verify_customer(s3, email="tom.whitfield@example.com", postcode="M1 4BT")
payload, decision, _ = tools.initiate_return(s3, order_id="ORD-84420", item_id="ITM-1", reason="too heavy")
check("GBP 342 order blocked from autonomous refund", payload.get("refused") is True)
check("rule is the value cap", payload.get("rule") == "refund.above_auto_cap", payload)
check("model is told a human can still do it", payload.get("next_step") == "escalate_to_human")

print("\nDuplicate return guard")
payload, _, _ = tools.initiate_return(s3, order_id="ORD-84501", item_id="ITM-1", reason="changed mind")
check("order with return in progress is blocked",
      payload.get("rule") == "return.already_in_progress", payload)

print("\nSuccessful action, then repeat")
s4 = Session()
tools.verify_customer(s4, email="priya.raman@example.com", postcode="SW1A 1AA")
payload, _, _ = tools.initiate_return(s4, order_id="ORD-84201", item_id="ITM-2", reason="duplicate copy")
check("eligible return succeeds", payload.get("ok") is True, payload)
check("refund amount comes from the item, not the order total", payload.get("refund_amount") == 14.99)
payload, _, _ = tools.initiate_return(s4, order_id="ORD-84201", item_id="ITM-1", reason="second attempt")
check("second return on same order now blocked",
      payload.get("rule") == "return.already_in_progress", payload)

print("\nPolicy grounding")
hits = policy.search_policy("how long do i have to return a book")
check("returns question retrieves the returns passage",
      any(h["passage_id"] == "POL-RET-01" for h in hits), hits)
hits = policy.search_policy("my book arrived damaged")
check("damage question retrieves the damage passage",
      any(h["passage_id"] == "POL-REF-02" for h in hits), hits)
hits = policy.search_policy("do you sell audiobooks on vinyl")
check("out-of-scope question retrieves nothing", hits == [], hits)
payload, _, cited = tools.search_policy(Session(), query="do you sell audiobooks on vinyl")
check("empty retrieval instructs a handoff", payload.get("found") is False and "human" in payload["instruction"])
check("no passages cited when nothing found", cited == [])

print("\nClarification is forced by the data")
s5 = Session()
tools.verify_customer(s5, email="priya.raman@example.com", postcode="SW1A 1AA")
payload, _, _ = tools.find_orders(s5)
open_orders = [o for o in payload["orders"] if o["status"] != "cancelled"]
check("test customer genuinely has multiple orders, so 'my order' is ambiguous",
      len(open_orders) >= 2, f"{len(open_orders)} orders")

print("\nTiered authority")
check("refunds are tier 2", guardrails.tier_of("initiate_return") == 2)
check("recommendations are tier 0", guardrails.tier_of("recommend_books") == 0)
check("book clubs are tier 0", guardrails.tier_of("find_book_clubs") == 0)
check("order reads are tier 1", guardrails.tier_of("get_order") == 1)
check("unknown tools default to the STRICTEST tier", guardrails.tier_of("delete_everything") == 2,
      "fail-closed, not fail-open")

print("\nRecommendations are ungated but grounded")
s6 = Session()
payload, _, _ = tools.recommend_books(s6, liked_title="Piranesi")
check("recommendation works with no verification", payload.get("found") is True, payload)
titles = {r["title"] for r in payload["recommendations"]}
check("every suggestion exists in the catalogue",
      all(any(b["title"] == t for b in catalogue.CATALOGUE.values()) for t in titles), titles)
check("nothing out of stock is suggested",
      all(catalogue.find_by_title(t)["in_stock"] for t in titles), titles)
check("the seed book is not suggested back", "Piranesi" not in titles, titles)
check("every suggestion carries a reason",
      all(r.get("why") for r in payload["recommendations"]))

payload, _, _ = tools.recommend_books(s6, liked_title="Dune")
check("off-catalogue seed returns nothing rather than a guess",
      payload.get("found") is False and payload["recommendations"] == [], payload)
check("agent is instructed not to guess which book was meant",
      "do not guess" in payload["instruction"].lower())

print("\nPersonalisation inherits the identity gate")
s7 = Session()
payload, _, _ = tools.recommend_books(s7, use_purchase_history=True)
check("history-based recommendation refused before verification", payload.get("refused") is True)
check("but the agent is told it can still recommend without history",
      "without history" in payload.get("instruction", "").lower(), payload)
tools.verify_customer(s7, email="priya.raman@example.com", postcode="SW1A 1AA")
payload, _, _ = tools.recommend_books(s7, use_purchase_history=True)
check("works after verification", payload.get("found") is True)
owned = {"The Fifth Season", "Piranesi", "Babel", "Sea of Tranquility", "Klara and the Sun"}
suggested = {r["title"] for r in payload["recommendations"]}
check("does not recommend books the customer already owns", not (suggested & owned),
      suggested & owned)

print("\nBook clubs are grounded")
payload, _, _ = tools.find_book_clubs(s6, about_title="Sea of Tranquility")
check("real club returned for a real book", payload.get("found") is True)
club = payload["clubs"][0]
check("club id exists in the data", club["club_id"] in catalogue.BOOK_CLUBS)
check("meeting date comes from the data",
      club["next_meeting"] == catalogue.BOOK_CLUBS[club["club_id"]]["next_meeting"])
payload, _, _ = tools.find_book_clubs(s6, about_title="Dune")
check("no club invented for an off-catalogue book", payload.get("found") is False)
check("agent instructed not to invent one", "invent" in payload["instruction"].lower())

total, passed = len(results), sum(results)
print(f"\n{passed}/{total} checks passed\n")
sys.exit(0 if passed == total else 1)
