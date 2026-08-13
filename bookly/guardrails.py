"""
The permission checks. This file decides what is allowed.

The AI can ask for anything. It cannot do anything. Every request for account
data or money comes through here first, and this file answers yes or no.

Notice what this file does NOT import: nothing to do with the AI, the
conversation, or what the customer said. It only sees a session and an order. So
there is nothing here to argue with. A customer can be as persuasive as they
like and it changes none of these numbers.

Checks return a Decision object instead of raising an error, because a refusal
is not a malfunction. Nothing has gone wrong; the system worked. It also means
we can log refusals and count them.

Money is handled in integer pence throughout. Floats are the wrong type for
money: 0.1 + 0.2 does not equal 0.3, and a cap comparison that is off by a
hundredth of a penny is a cap you cannot reason about.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


RETURN_WINDOW_DAYS = 30

# Per refund, in pence. Checked against the money actually leaving, not the order
# total. In production this belongs in a settings service a support manager owns,
# still resolved here, outside the model.
AUTO_REFUND_CAP_PENCE = 10_000  # £100.00

MAX_VERIFICATION_ATTEMPTS = 3


def pounds(pence: int) -> str:
    """Format pence for a human. Presentation only, never arithmetic."""
    return f"{pence / 100:.2f}"


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
    What we remember about this conversation, kept on our side.

    The important field is verified_customer_id. It lives here, in code, not in
    the chat history. If the AI kept track of who was verified, a customer could
    simply claim they had verified earlier and it might believe them. One of the
    tests tries exactly that.

    Only one thing can set this field: a verify_customer call that matched.

    Failed verification attempts are counted HERE, per session, and nowhere else.
    An earlier version counted them against the email address in a durable store,
    which meant anyone could lock any customer out of support by guessing three
    postcodes against their email. That is an unauthenticated denial of service,
    and it was worse than the problem it replaced. Rate limiting by source belongs
    at the transport layer, where a request actually has one.
    """

    verified_customer_id: Optional[str] = None
    verification_attempts: int = 0
    escalated: bool = False
    actions_taken: list = field(default_factory=list)

    MAX_VERIFICATION_ATTEMPTS = MAX_VERIFICATION_ATTEMPTS


def check_identity(session: Session, tool_name: str) -> Decision:
    """Nothing about a customer's account can be read until they prove who they are."""
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


# What the dispatcher must run before each tool, by name.
#
# Until now the tiers were a description and enforcement was a convention: each
# handler remembered to call its own checks. A convention fails open. Add a tool
# and forget the check, and nothing complains.
#
# agent.py consults this table before calling any handler. A tool absent from the
# table is refused, so the next tool someone adds fails closed. A test walks
# HANDLERS and fails if any name is missing here.
TOOL_POLICY: dict[str, tuple] = {
    "verify_customer":    (),
    "search_policy":      (),
    "recommend_books":    (),

    "escalate_to_human":  (),
    "find_orders":        ("identity",),
    "get_order":          ("identity",),
    "initiate_return":    ("identity",),
}


def check_dispatch(session: Session, tool_name: str) -> Decision:
    """
    Gate every tool call before the handler runs.

    Returns the first failure. Handlers still run their own checks, because the
    ones needing the order or the amount cannot be resolved from a tool name
    alone. This layer catches the case a handler forgets.
    """
    required = TOOL_POLICY.get(tool_name)
    if required is None:
        return Decision(
            False,
            "dispatch.unknown_tool",
            f"No policy defined for '{tool_name}'. Refusing rather than guessing.",
        )
    for name in required:
        if name == "identity":
            d = check_identity(session, tool_name)
            if not d.permitted:
                return d
    return Decision(True, "dispatch.permitted", f"Policy satisfied for {tool_name}.")


def check_ownership(session: Session, order: dict) -> Decision:
    """
    Even a verified customer only sees their own orders.

    Showing one customer another customer's data is the worst thing this agent
    could do. So it is prevented here, in code, rather than by asking the AI to
    be careful about it.
    """
    if order["customer_id"] != session.verified_customer_id:
        return Decision(
            False,
            "ownership.mismatch",
            # Says "not found on this account", matching what get_order tells the
            # customer. "Not yours" would confirm the order exists, letting
            # someone fish for valid order numbers. Two places said two different
            # things, which defeated the point of either.
            "No order found with that reference on this account.",
        )
    return Decision(True, "ownership.ok", "Order belongs to the verified customer.")


def check_verification_attempts(session: Session) -> Decision:
    """
    Stop someone guessing postcodes until one works.

    Counted per session, and nowhere else. An earlier version counted against the
    email in a durable store, so anyone could lock any customer out of support by
    guessing three postcodes against their address. Unauthenticated denial of
    service, and worse than the reconnect problem it was meant to solve.

    Rate limiting by source needs a source, which this layer does not have. That
    belongs at the transport, with a TTL. `email` is accepted and ignored so the
    caller does not have to change.
    """
    if session.verification_attempts >= Session.MAX_VERIFICATION_ATTEMPTS:
        return Decision(
            False,
            "identity.attempts_exceeded",
            "Too many failed verification attempts. Hand off to a human agent.",
        )
    return Decision(True, "identity.attempts_ok", "Within attempt limit.")


def check_returnable(order: dict, today: Optional[date] = None) -> Decision:
    """
    Can this order be returned? Worked out from dates and status, never from
    what the customer said.

    Three separate reasons, reported separately on purpose. "You cannot return
    this" and "you cannot return this yet" need very different replies.
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

    if not order.get("delivered_date"):
        # Status says delivered but no date landed. Refuse rather than crash on
        # fromisoformat(None), and say what is actually wrong.
        return Decision(
            False,
            "return.no_delivery_date",
            "This order has no delivery date recorded, so the return window "
            "cannot be checked. A colleague needs to look at it.",
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


def check_refund_value(order: dict, pence: Optional[int] = None
) -> Decision:
    """
    How much money the agent may move on its own. Two limits, two jobs.

    Checked against `pence`, the money actually leaving the business. An earlier version checked the order total,
    which over-blocked: returning one £20 book from a £120 order needed a human
    for no reason.

    Above the cap the agent still does the work: verifies, finds the order,
    explains the position, takes the reason. A person approves the payment.

    """
    # No amount given means the caller has not picked an item yet, so fall back
    # to the order total and stay conservative.
    pence = int(order["total_pence"]) if pence is None else int(pence)
    cur = order["currency"]

    if pence > AUTO_REFUND_CAP_PENCE:
        return Decision(
            False,
            "refund.above_auto_cap",
            f"Refund of {cur} {pounds(pence)} is over the per-refund limit of "
            f"{cur} {pounds(AUTO_REFUND_CAP_PENCE)}. Requires human approval.",
        )

    return Decision(
        True,
        "refund.within_auto_cap",
        f"Refund of {cur} {pounds(pence)} is inside both limits.",
    )


def authorise_return(
    session: Session,
    order: dict,
    pence: Optional[int] = None,
    today: Optional[date] = None,
) -> Decision:
    """
    All the checks for the one action that moves money, in order.

    Identity, then ownership, then eligibility, then value. We stop at the first
    failure, and the order matters. If an unverified person asks about a
    104-day-old order, they should be told to verify, not told about the return
    window. Deal with the most basic problem first.

    `pence` is the money actually being refunded, in integer pence. Pass it, or
    the value check falls back to the order total and over-blocks.
    """
    for decision in (
        check_identity(session, "initiate_return"),
        check_ownership(session, order),
        check_returnable(order, today=today),
        check_refund_value(order, pence=pence),
    ):
        if not decision.permitted:
            return decision
    return Decision(True, "return.authorised", "All checks passed.")


# Why there is no check_recommendation() in this file
#
# Suggesting a book needs no permission check at all. If the agent picks badly,
# the customer says "not for me" and nothing is lost. A check here would add
# friction and protect nobody.
#
# There IS one rule about recommendations, but it belongs elsewhere: the agent
# may only name books that are actually in the catalogue and in stock. That is
# about telling the truth, not about permission, so it lives in the tool. See
# recommend_books in tools.py.
#
# Being able to explain why something has no check is as much a decision as
# adding one.
