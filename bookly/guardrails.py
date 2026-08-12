"""
The control layer.

One question: given the session state, is this action permitted? This module
never sees the model, the conversation, or the customer's words, so it cannot be
persuaded.

The AI proposes. This decides. Different jobs, different places.

Decisions are returned, never raised, so a refusal is a loggable outcome rather
than an exception the agent has to interpret.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# Business rules, in one place, as named constants. In production these move to
# a policy service so CX operations can change them without a deploy. They still
# resolve outside the model.

RETURN_WINDOW_DAYS = 30
AUTO_REFUND_CAP_GBP = 100.00
IDENTITY_REQUIRED_FOR = {"find_orders", "get_order", "initiate_return"}


# Tiered authority, sorted by recoverability.
#
#   Tier 0  informational   no gate      mistake costs a correction
#   Tier 1  account read    identity     mistake leaks someone's data
#   Tier 2  irreversible    full chain   mistake costs money and trust
#
# Lock down the money and the same architecture can afford to be generous with
# recommendations. Calibration, not lockdown.

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
    What the guardrails need to know about the conversation so far.

    Identity lives here, not in the transcript. If the model tracked it in its
    own context a customer could talk their way into it. One code path sets it:
    a successful verify_customer call.
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
    A verified customer sees only their own orders.

    Stops the worst failure available to a support agent, and does it here
    rather than by asking the model to be careful.
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
    Return eligibility, resolved from data and dates, never from the
    conversation.

    Three rules reported separately. "You cannot return this" and "you cannot
    return this yet" are different conversations.
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

    Above the cap the agent still does the work: verify, look up, explain,
    gather the reason. A human authorises the money. Most enterprise buyers want
    exactly this, which makes "how much can it do alone" a configuration
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

    Ordered identity, ownership, eligibility, value. The first failure wins, so
    the customer hears the most fundamental reason rather than an incidental one.
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


# Tier 0 note
#
# There is deliberately no check_recommendation(). A recommendation is fully
# recoverable. Suggest a book the customer does not fancy and they say so.
# Gating it would add friction and protect nobody.
#
# The one constraint is grounding, not authority: suggestions must resolve to a
# real in-stock catalogue entry. That lives in the tool, since it concerns
# truthfulness. See tools.recommend_books.
#
# Saying why an action has no guardrail is part of the design.
