"""
The control layer.

This module answers one question: given the current session state, is this
action permitted? It has no knowledge of the language model, the conversation,
or how the request was phrased. It cannot be persuaded, because it never reads
the customer's words.

This is the architectural claim of the whole submission. The model decides what
to ATTEMPT. This module decides what is PERMITTED. Those are different jobs and
they belong in different places.

Every decision returns a Decision object rather than raising, so that a refusal
is a first-class, loggable outcome rather than an exception the agent has to
interpret.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# --------------------------------------------------------------------------
# Business rules. These live in code, in one place, as named constants.
#
# In production these move to a policy service so that CX operations can change
# them without a deploy -- but they still resolve OUTSIDE the model.
# --------------------------------------------------------------------------

RETURN_WINDOW_DAYS = 30
AUTO_REFUND_CAP_GBP = 100.00
IDENTITY_REQUIRED_FOR = {"find_orders", "get_order", "initiate_return"}


# --------------------------------------------------------------------------
# Tiered authority.
#
# The obvious objection to putting constraints in code is that it produces a
# system too restrictive to be useful. That objection assumes all actions
# deserve the same suspicion. They do not.
#
# The right axis is RECOVERABILITY. If an action is easy to undo, the agent
# should be allowed to take it freely, because the cost of a mistake is close
# to zero and the cost of over-caution is a worse customer experience. If an
# action cannot be undone, it gets the full chain.
#
#   Tier 0  informational   no gate      wrong answer costs a correction
#   Tier 1  account read    identity     wrong answer leaks someone's data
#   Tier 2  irreversible    full chain   wrong answer costs money and trust
#
# This is what lets the same architecture be strict about refunds and generous
# about recommendations. It is a calibration, not a lockdown -- and it is the
# reason a control layer makes an agent MORE capable rather than less.
# --------------------------------------------------------------------------

ACTION_TIERS = {
    "search_policy": 0,
    "recommend_books": 0,
    "find_book_clubs": 0,
    "escalate_to_human": 0,
    "verify_customer": 0,
    "find_orders": 1,
    "get_order": 1,
    "initiate_return": 2,
}

TIER_NAMES = {0: "informational", 1: "account read", 2: "irreversible"}


def tier_of(tool_name: str) -> int:
    """Unknown tools default to the strictest tier, not the loosest."""
    return ACTION_TIERS.get(tool_name, 2)


@dataclass
class Decision:
    """The outcome of a permission check."""

    permitted: bool
    rule: str
    reason: str

    def as_dict(self):
        return {"permitted": self.permitted, "rule": self.rule, "reason": self.reason}


@dataclass
class Session:
    """
    Everything the guardrails need to know about the conversation so far.

    Identity lives here, not in the conversation transcript. That matters: if
    verified_customer_id were something the model tracked in its own context, a
    customer could talk their way into it. Here, it is set by exactly one code
    path -- a successful verify_customer call -- and read by the guardrails.
    """

    verified_customer_id: Optional[str] = None
    verification_attempts: int = 0
    escalated: bool = False
    actions_taken: list = field(default_factory=list)

    MAX_VERIFICATION_ATTEMPTS = 3


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_identity(session: Session, tool_name: str) -> Decision:
    """No account data is reachable until identity is established."""
    if tool_name not in IDENTITY_REQUIRED_FOR:
        return Decision(True, "identity.not_required", "Tool does not touch account data.")

    if session.verified_customer_id is None:
        return Decision(
            False,
            "identity.unverified",
            "Customer identity has not been verified. Verify with email and postcode "
            "before accessing any order data.",
        )
    return Decision(True, "identity.verified", f"Verified as {session.verified_customer_id}.")


def check_ownership(session: Session, order: dict) -> Decision:
    """
    A verified customer can only see their own orders.

    This is the check that stops the most damaging failure mode in a support
    agent: leaking one customer's data to another. It is enforced here rather
    than by asking the model to be careful.
    """
    if order["customer_id"] != session.verified_customer_id:
        return Decision(
            False,
            "ownership.mismatch",
            "That order does not belong to the verified customer.",
        )
    return Decision(True, "ownership.ok", "Order belongs to the verified customer.")


def check_verification_attempts(session: Session) -> Decision:
    """Rate limit identity guessing."""
    if session.verification_attempts >= Session.MAX_VERIFICATION_ATTEMPTS:
        return Decision(
            False,
            "identity.attempts_exceeded",
            "Too many failed verification attempts. Hand off to a human agent.",
        )
    return Decision(True, "identity.attempts_ok", "Within attempt limit.")


def check_returnable(order: dict, today: Optional[date] = None) -> Decision:
    """
    Return eligibility, resolved from data and dates -- never from the
    conversation.

    Three separate rules, each reported distinctly, because "you cannot return
    this" and "you cannot return this YET" are different customer experiences
    and the agent needs to say the right one.
    """
    today = today or date.today()

    if order.get("return_status") is not None:
        return Decision(
            False,
            "return.already_in_progress",
            f"A return is already {order['return_status']} for this order.",
        )

    if order["status"] != "delivered":
        return Decision(
            False,
            "return.not_delivered",
            f"Order status is '{order['status']}'. Returns can only start after delivery.",
        )

    delivered = date.fromisoformat(order["delivered_date"])
    age = (today - delivered).days

    if age > RETURN_WINDOW_DAYS:
        return Decision(
            False,
            "return.window_expired",
            f"Delivered {age} days ago. The return window is {RETURN_WINDOW_DAYS} days.",
        )

    return Decision(
        True,
        "return.eligible",
        f"Delivered {age} days ago, inside the {RETURN_WINDOW_DAYS} day window.",
    )


def check_refund_value(order: dict) -> Decision:
    """
    Value ceiling on autonomous action.

    Above the cap the agent may still do all the work -- verify, look up,
    explain, gather the reason -- but a human authorises the money. This is
    the pattern most enterprise buyers actually want, and it is why "how much
    can it do on its own" is a configuration question rather than a capability
    question.
    """
    if order["total"] > AUTO_REFUND_CAP_GBP:
        return Decision(
            False,
            "refund.above_auto_cap",
            f"Order value {order['currency']} {order['total']:.2f} exceeds the "
            f"autonomous limit of GBP {AUTO_REFUND_CAP_GBP:.2f}. Requires human approval.",
        )
    return Decision(
        True,
        "refund.within_auto_cap",
        f"Order value {order['currency']} {order['total']:.2f} is within the autonomous limit.",
    )


def authorise_return(session: Session, order: dict, today: Optional[date] = None) -> Decision:
    """
    Full authorisation chain for the one action that moves money.

    Ordered deliberately: identity, then ownership, then eligibility, then
    value. The first failure short-circuits, so the reason surfaced to the
    customer is the most fundamental one rather than an incidental one.
    """
    for decision in (
        check_identity(session, "initiate_return"),
        check_ownership(session, order),
        check_returnable(order, today=today),
        check_refund_value(order),
    ):
        if not decision.permitted:
            return decision
    return Decision(True, "return.authorised", "All checks passed.")


# --------------------------------------------------------------------------
# Tier 0 note
#
# There is deliberately no check_recommendation() function.
#
# That absence is the point. A recommendation is fully recoverable -- if the
# agent suggests a book the customer does not fancy, they say so and the
# conversation continues. Gating it would add friction and protect nobody.
#
# The one constraint on recommendations is not a permission check at all, it is
# a grounding constraint: suggestions must resolve to a real catalogue entry
# that is in stock. That lives in the tool, not here, because it is about
# truthfulness rather than authority. See tools.recommend_books.
#
# Being able to say clearly WHY a given action has no guardrail is as much a
# part of the design as the guardrails themselves.
# --------------------------------------------------------------------------
