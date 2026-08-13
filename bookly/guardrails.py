"""
The permission checks. This file decides what is allowed.

The AI can ask for anything. It cannot do anything. Every request for account
data or money comes through here first, and this file answers yes or no.

Notice what this file does NOT import: nothing to do with the AI, the
conversation, or what the customer said. It only sees a session and an order. So
there is nothing here to argue with. A customer can be as persuasive as they
like and it changes none of these numbers.

That is the whole point. Written in the AI's instructions, a rule is a request.
Written here, it is a rule.

Checks return a Decision object instead of raising an error, because a refusal
is not a malfunction. Nothing has gone wrong; the system worked. It also means
we can log refusals and count them.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# The actual business rules, in one place so they are easy to find and change.
# In a real deployment these would move to a settings service so a support
# manager could change them without a developer. They would still be resolved
# here, outside the AI.

RETURN_WINDOW_DAYS = 30

# Per refund. Checked against the money actually leaving the business, not the
# order total.
AUTO_REFUND_CAP_GBP = 100.00

# Per customer, rolling. Without this, four separate GBP 75 refunds each pass the
# per-refund cap and GBP 300 leaves unsupervised. One cap limits a decision. You
# also need one limiting a sequence, and it has to survive a reconnect.
AUTO_REFUND_SESSION_CAP_GBP = 150.00


IDENTITY_REQUIRED_FOR = {"find_orders", "get_order", "initiate_return"}


# Not every action deserves the same suspicion. Sort them by one question:
# if this goes wrong, can we undo it?
#
#   Tier 0  no checks       Suggest a book. Wrong? They say so, you move on.
#   Tier 1  prove identity  Read their orders. Wrong? Someone sees another
#                           customer's private data.
#   Tier 2  every check     Refund money. Wrong? It cannot be pulled back.
#
# Locking down the money is what lets the agent be relaxed about everything
# else. Without tier 2 being airtight, we would have to be nervous about tier 0
# too.

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
    What we remember about this conversation, kept on our side.

    The important field is verified_customer_id. It lives here, in code, not in
    the chat history. If the AI kept track of who was verified, a customer could
    simply claim they had verified earlier and it might believe them. One of the
    tests tries exactly that.

    Only one thing can set this field: a verify_customer call that matched.
    """

    verified_customer_id: Optional[str] = None
    verification_attempts: int = 0
    escalated: bool = False
    actions_taken: list = field(default_factory=list)
    # Money already approved in this conversation. Read by check_refund_value,
    # written by initiate_return only after a refund actually succeeds.
    refunded_so_far: float = 0.0
    # Idempotency keys for refunds already completed, so a duplicate does not
    # depend on the mock data having been mutated in this process.
    completed_returns: set = field(default_factory=set)

    MAX_VERIFICATION_ATTEMPTS = 3


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


# with a rolling window. The invariant is the same either way: the counter has
# to outlive the conversation or the cap is decoration.
_REFUND_TOTALS: dict[str, float] = {}
_FAILED_VERIFICATIONS: dict[str, int] = {}


def refunded_by(customer_id: Optional[str]) -> float:
    """Money already approved for this customer, across conversations."""
    return _REFUND_TOTALS.get(customer_id or "", 0.0)


def record_refund(customer_id: Optional[str], amount: float) -> None:
    key = customer_id or ""
    _REFUND_TOTALS[key] = _REFUND_TOTALS.get(key, 0.0) + amount


def failed_verifications(identifier: str) -> int:
    """Failed attempts against this email, across conversations."""
    return _FAILED_VERIFICATIONS.get((identifier or "").strip().lower(), 0)


def record_failed_verification(identifier: str) -> None:
    key = (identifier or "").strip().lower()
    _FAILED_VERIFICATIONS[key] = _FAILED_VERIFICATIONS.get(key, 0) + 1


def reset_stores() -> None:
    """Clear both counters. Tests call this. Production would not."""
    _REFUND_TOTALS.clear()
    _FAILED_VERIFICATIONS.clear()


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
TOOL_POLICY: dict[str, tuple[str, ...]] = {
    "verify_customer":    (),
    "search_policy":      (),
    "recommend_books":    (),
    "find_book_clubs":    (),
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


def check_verification_attempts(session: Session, email: str = "") -> Decision:
    """
    Stop someone guessing postcodes until one works.

    Counts against the email, in a store outliving the conversation. The old
    version counted on the Session, so reconnecting reset the counter and the
    guard did nothing.
    """
    if failed_verifications(email) >= Session.MAX_VERIFICATION_ATTEMPTS:
        return Decision(
            False,
            "identity.attempts_exceeded",
            "Too many failed verification attempts. Hand off to a human agent.",
        )
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


def check_refund_value(
    order: dict,
    amount: Optional[float] = None,
    session: Optional[Session] = None,
) -> Decision:
    """
    How much money the agent may move on its own. Two limits, two jobs.

    The per-refund cap bounds one decision, checked against `amount`, the money
    actually leaving the business. An earlier version checked order["total"]
    instead. Wrong, though in a safe direction: an item price is never more than
    the order total, so it over-blocked. Returning one GBP 20 book from a GBP 120
    order needed a human for no reason.

    The session cap bounds the conversation. Four separate GBP 75 refunds each
    pass the per-refund cap, and GBP 300 leaves unsupervised.

    Above either cap the agent still does the work: verifies, finds the order,
    explains the position, takes the reason. A person approves the payment. That
    turns "how much can it do unsupervised" into a setting.
    """
    # No amount given means the caller has not picked an item yet, so fall back
    # to the order total and stay conservative.
    amount = order["total"] if amount is None else amount
    cur = order["currency"]

    if amount > AUTO_REFUND_CAP_GBP:
        return Decision(
            False,
            "refund.above_auto_cap",
            f"Refund of {cur} {amount:.2f} is over the per-refund limit of "
            f"GBP {AUTO_REFUND_CAP_GBP:.2f}. Requires human approval.",
        )

    if session is not None:
        # Durable total, not the per-Session one. A reconnect used to reset this.
        running = refunded_by(session.verified_customer_id) + amount
        if running > AUTO_REFUND_SESSION_CAP_GBP:
            return Decision(
                False,
                "refund.above_session_cap",
                f"A refund of {cur} {amount:.2f} would take this customer to "
                f"{cur} {running:.2f}, over the rolling limit of "
                f"GBP {AUTO_REFUND_SESSION_CAP_GBP:.2f}. Requires human approval.",
            )

    return Decision(
        True,
        "refund.within_auto_cap",
        f"Refund of {cur} {amount:.2f} is inside both limits.",
    )


def authorise_return(
    session: Session,
    order: dict,
    amount: Optional[float] = None,
    today: Optional[date] = None,
) -> Decision:
    """
    All the checks for the one action that moves money, in order.

    Identity, then ownership, then eligibility, then value. We stop at the first
    failure, and the order matters. If an unverified person asks about a
    104-day-old order, they should be told to verify, not told about the return
    window. Deal with the most basic problem first.

    `amount` is the money actually being refunded. Pass it, or the value check
    falls back to the order total and over-blocks.
    """
    for decision in (
        check_identity(session, "initiate_return"),
        check_ownership(session, order),
        check_returnable(order, today=today),
        check_refund_value(order, amount=amount, session=session),
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
