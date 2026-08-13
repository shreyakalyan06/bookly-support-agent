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


# One table. Every tool gets a tier, and the tier decides which checks run.
#
# Sorted by one question: if this goes wrong, does it reverse?
#
#   0  informational   nothing to check   a mistake costs a correction
#   1  account read    prove identity     a mistake shows one customer another's data
#   2  irreversible    everything         a mistake moves money that stays moved
#
# Locking down tier 2 is what lets tier 0 stay open.
#
# There used to be a second table saying which tools needed identity, so a tool
# could be gated in one place and open in the other. Now the tier is the only
# thing to get right, and a test walks it.
ACTION_TIERS = {
    "verify_customer": 0,
    "search_policy": 0,
    "recommend_books": 0,
    "escalate_to_human": 0,
    "find_orders": 1,
    "get_order": 1,
    "initiate_return": 2,
}

TIER_NAMES = {0: "informational", 1: "account read", 2: "irreversible"}

# What each tier costs you at the dispatcher.
TIER_CHECKS = {
    0: (),
    1: ("identity",),
    2: ("identity", "not_escalated"),
}


def tier_of(tool_name: str) -> int:
    """Unknown tools land in the strictest tier, not the loosest."""
    return ACTION_TIERS.get(tool_name, 2)


def checks_for(tool_name: str) -> tuple:
    """The checks the dispatcher runs before this tool, derived from its tier."""
    return TIER_CHECKS[tier_of(tool_name)]


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



def check_identity(session: Session, tool_name: str) -> Decision:
    """Nothing about a customer's account can be read until they prove who they are."""
    if tier_of(tool_name) < 1:
        return Decision(True, "identity.not_required", "Tool does not touch account data.")

    if session.verified_customer_id is None:
        return Decision(
            False,
            "identity.unverified",
            "Customer identity has not been verified. Verify with email and postcode "
            "before accessing any order data.",
        )
    return Decision(True, "identity.verified", f"Verified as {session.verified_customer_id}.")


def check_dispatch(session: Session, tool_name: str) -> Decision:
    """
    Gate every tool call before the handler runs.

    Returns the first failure. Handlers still run their own checks, because the
    ones needing the order or the amount cannot be resolved from a tool name
    alone. This layer catches the case a handler forgets.
    """
    if tool_name not in ACTION_TIERS:
        return Decision(
            False,
            "dispatch.unknown_tool",
            f"No tier defined for '{tool_name}'. Refusing rather than guessing.",
        )
    for name in checks_for(tool_name):
        if name == "identity":
            d = check_identity(session, tool_name)
            if not d.permitted:
                return d
        elif name == "not_escalated":
            # Once a person owns the conversation the agent stops moving money
            # behind them.
            if session.escalated:
                return Decision(
                    False, "dispatch.already_escalated",
                    "This conversation has gone to a colleague. The agent does not "
                    "take irreversible actions after that.",
                )
        else:
            # An unknown name used to be skipped. So adding ("ownership",
            # "refund_cap") while dropping "identity" opened the money path while
            # the table read stricter than before. Refuse instead.
            return Decision(
                False, "dispatch.unknown_requirement",
                f"Tier {tier_of(tool_name)} names a check that does not exist: "
                f"'{name}'. Refusing rather than skipping it.",
            )
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
    belongs at the transport, with a TTL.
    """
    if session.verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
        return Decision(
            False,
            "identity.attempts_exceeded",
            "Too many failed verification attempts. Hand off to a human agent.",
        )
    return Decision(True, "identity.attempts_ok", "Within attempt limit.")


def check_returnable(order: dict, item_id: str = "",
                     today: Optional[date] = None) -> Decision:
    """
    Can this item be returned? Worked out from dates and status, never from what
    the customer said.

    The reasons are reported separately on purpose. "You cannot return this" and
    "you cannot return this yet" need very different replies.
    """
    today = today or date.today()

    # Per item, not per order. An order-level flag meant returning one book from
    # a two book order blocked the other, which is the commonest return there is.
    if item_id and item_id in order.get("returned_item_ids", ()):
        return Decision(
            False,
            "return.already_in_progress",
            "A return is already in progress for that item.",
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
    How much money the agent may move on its own.

    Checked against `pence`, the money actually leaving. An earlier version checked
    the order total, which over-blocked: returning one £20 book from a £120 order
    needed a human for no reason.

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
        f"Refund of {cur} {pounds(pence)} is inside the limit.",
    )


def authorise_return(
    session: Session,
    order: dict,
    item_id: str = "",
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
        check_returnable(order, item_id=item_id, today=today),
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
