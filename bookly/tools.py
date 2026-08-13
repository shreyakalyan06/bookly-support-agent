"""
The list of things the AI is allowed to ask for, and the code that does them.

Two halves. TOOL_SCHEMAS is the menu we hand the AI: eight jobs, each with a
description and the information it must supply. HANDLERS is what actually runs
when it asks.

Two rules shape everything below.

Anything touching a customer's account or money runs the permission checks in
guardrails.py FIRST, before doing any work. If a check says no, we send back a
refusal. The AI cannot get round it, because asking was the only thing it could
ever do.

Handlers return data, not sentences. We send facts; the AI turns them into
something a person wants to read. Keeping those jobs apart means the system does
not depend on the AI reading a sentence correctly.
"""

from datetime import date
from . import catalogue, data, guardrails, policy
from .guardrails import Decision, Session

# The menu we hand the AI.
#
# The "description" is not documentation for us. It is the only thing telling
# the AI when to use each tool, so it is written as instructions to it.

TOOL_SCHEMAS = [
    {
        "name": "verify_customer",
        "description": (
            "Verify a customer's identity using their email address and postcode. "
            "This must succeed before any order information can be accessed. "
            "Do not guess or assume either value, ask the customer for both."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "The email address on the account."},
                "postcode": {"type": "string", "description": "The billing postcode on the account."},
            },
            "required": ["email", "postcode"],
        },
    },
    {
        "name": "find_orders",
        "description": (
            "List all orders belonging to the verified customer, most recent first. "
            "Use this when the customer asks about an order but has not given an order "
            "number. If more than one order could match what they described, ask them "
            "which one rather than choosing."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_order",
        "description": "Retrieve the full detail of one order, including items, tracking and return eligibility.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order reference, e.g. ORD-84201."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "search_policy",
        "description": (
            "Search Bookly's published policies. Use this for ANY question about shipping, "
            "returns, refunds, cancellations, gift cards or account access. You must call "
            "this before stating a policy, and you must cite the passage_id you relied on. "
            "If it returns no passages, say you do not have that information and offer a "
            "human, do not answer from general knowledge."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The customer's question, in their words."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "initiate_return",
        "description": (
            "Start a return for one item on a delivered order. This moves money, so "
            "eligibility and value checks may refuse it. Collect the reason for the "
            "return from the customer before calling this. A refusal on value means a "
            "colleague must approve, not that the return is impossible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "item_id": {"type": "string", "description": "The item_id from the order detail."},
                "reason": {
                    "type": "string",
                    "description": "The customer's stated reason, in their own words.",
                },
            },
            "required": ["order_id", "item_id", "reason"],
        },
    },
    {
        "name": "recommend_books",
        "description": (
            "Suggest books from Bookly's catalogue. Use this whenever a customer is deciding "
            "what to read, has finished something, didn't get on with a book, or asks what "
            "else you have.\n\n"
            "Give `liked_title` when they name a book they enjoyed. Give `mood` or `themes` "
            "when they describe what they're after rather than naming something. If the "
            "customer is verified you may pass use_purchase_history to draw on what they have "
            "already bought.\n\n"
            "You may only recommend books this tool returns. Never suggest a title from your "
            "own knowledge, even if you are confident Bookly stocks it, a recommendation for "
            "something we cannot sell creates a support problem rather than solving one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "liked_title": {
                    "type": "string",
                    "description": "A book the customer enjoyed, to find similar titles.",
                },
                "mood": {
                    "type": "string",
                    "description": "Atmosphere they're after, e.g. dreamlike, warm, propulsive, bleak, witty.",
                },
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subjects of interest, e.g. cats, memory, myth retelling, court politics.",
                },
                "use_purchase_history": {
                    "type": "boolean",
                    "description": "Base suggestions on this customer's previous orders. Requires verification.",
                },
                "shop_cat_picks_only": {
                    "type": "boolean",
                    "description": "Limit to Tiberius's staff-picks shelf.",
                },
            },
        },
    },
    {
        "name": "find_book_clubs",
        "description": (
            "Find Bookly reading groups. Use this when a customer mentions wanting to talk "
            "about a book, is unsure whether they'll get on with something, or when a return "
            "or refusal has left them without a good outcome, an invitation to a group "
            "discussing that book is often a better ending than an apology.\n\n"
            "Only mention clubs this tool returns, with their real meeting date and size."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "about_title": {
                    "type": "string",
                    "description": "Find clubs reading or thematically close to this book.",
                },
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Find clubs by subject interest instead of by book.",
                },
            },
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the conversation to a human agent. Use this when a guardrail refuses an "
            "action the customer still needs, when policy search returns nothing, when the "
            "customer asks for a human, or when you are uncertain. Always include a summary "
            "so the customer does not have to repeat themselves."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why this needs a human."},
                "summary": {
                    "type": "string",
                    "description": "What has happened so far and what the customer needs.",
                },
            },
            "required": ["reason", "summary"],
        },
    },
]


# The handlers: what actually happens when the AI asks.
#
# Each returns three things:
#   1. the answer we send back to the AI
#   2. the permission decision, so we can log WHY something was allowed
#   3. any policy references quoted, so we can check the AI cited them


def _refusal(decision: Decision):
    """
    Build a refusal.

    We return a refusal instead of raising an error, for three reasons. The AI
    needs to be told, and an error would never reach it. Nothing has actually
    gone wrong, so an error would be misleading. And because every refusal has
    the same shape, we can count them later.
    """
    return {
        "ok": False,
        "refused": True,
        "rule": decision.rule,
        "reason": decision.reason,
    }


def verify_customer(session: Session, email: str = "", postcode: str = "", **_):
    attempts_ok = guardrails.check_verification_attempts(session, email=email)
    if not attempts_ok.permitted:
        return _refusal(attempts_ok), attempts_ok.as_dict(), []

    customer = data.get_customer_by_email(email)
    postcode_norm = (postcode or "").replace(" ", "").upper()

    if customer is None or customer["postcode"].replace(" ", "").upper() != postcode_norm:
        session.verification_attempts += 1
        guardrails.record_failed_verification(email)
        remaining = Session.MAX_VERIFICATION_ATTEMPTS - session.verification_attempts
        return (
            {
                "ok": False,
                "verified": False,
                "reason": "Email and postcode did not match an account.",
                "attempts_remaining": max(remaining, 0),
            },
            {"permitted": True, "rule": "identity.attempt_failed", "reason": "Credentials did not match."},
            [],
        )

    session.verified_customer_id = customer["customer_id"]
    return (
        {
            "ok": True,
            "verified": True,
            "customer_name": customer["name"],
            "customer_id": customer["customer_id"],
        },
        {"permitted": True, "rule": "identity.verified", "reason": "Credentials matched."},
        [],
    )


def find_orders(session: Session, **_):
    gate = guardrails.check_identity(session, "find_orders")
    if not gate.permitted:
        return _refusal(gate), gate.as_dict(), []

    orders = data.get_orders_for_customer(session.verified_customer_id)
    orders.sort(key=lambda o: o["placed_date"], reverse=True)

    return (
        {
            "ok": True,
            "count": len(orders),
            "orders": [
                {
                    "order_id": o["order_id"],
                    "status": o["status"],
                    "placed_date": o["placed_date"],
                    "delivered_date": o.get("delivered_date"),
                    "total": o["total"],
                    "currency": o["currency"],
                    "item_titles": [i["title"] for i in o["items"]],
                }
                for o in orders
            ],
        },
        gate.as_dict(),
        [],
    )


def get_order(session: Session, order_id: str = "", **_):
    gate = guardrails.check_identity(session, "get_order")
    if not gate.permitted:
        return _refusal(gate), gate.as_dict(), []

    order = data.get_order(order_id)
    if order is None:
        return (
            {"ok": False, "reason": NOT_FOUND},
            gate.as_dict(),
            [],
        )

    owned = guardrails.check_ownership(session, order)
    if not owned.permitted:
        # Deliberately does not reveal that the order exists.
        return (
            {"ok": False, "reason": NOT_FOUND},
            owned.as_dict(),
            [],
        )

    returnable = guardrails.check_returnable(order)
    # No item chosen yet, so this checks the order total. Conservative on
    # purpose: it flags a possible approval step before the customer picks.
    value = guardrails.check_refund_value(order, session=session)

    return (
        {
            "ok": True,
            "order": {
                k: v for k, v in order.items() if k != "customer_id"
            },
            # We work out whether it can be returned and tell the AI the
            # answer. We do not hand it two dates and hope it does the sums.
            "return_eligibility": {
                "returnable": returnable.permitted,
                "rule": returnable.rule,
                "reason": returnable.reason,
                # Telling the AI up front means it can decline politely
                # instead of trying and being blocked. If it tried anyway,
                # authorise_return would still stop it. Two safety nets.
                # Tell the AI about both possible blockers, not just the date.
                #
                # First version only mentioned the return window. So a £342
                # order bought last week looked completely fine, the AI would
                # try to refund it, get refused, and the customer would watch
                # the system trip over itself. Now it knows up front and can say
                # "a colleague needs to approve this" before trying.
                "surfaced_constraint": (
                    returnable.rule
                    if not returnable.permitted
                    else (value.rule if not value.permitted else None)
                ),
                "requires_human_approval": not value.permitted,
                "value_note": value.reason,
            },
        },
        gate.as_dict(),
        [],
    )


def search_policy(session: Session, query: str = "", **_):
    hits = policy.search_policy(query)

    if not hits:
        return (
            {
                "ok": True,
                "found": False,
                "passages": [],
                "instruction": (
                    "No policy passage matched. Tell the customer you do not have that "
                    "information and offer to pass them to a human. Do not answer from "
                    "general knowledge."
                ),
            },
            None,
            [],
        )

    return (
        {
            "ok": True,
            "found": True,
            "passages": hits,
            "instruction": "Answer only from these passages and cite the passage_id you used.",
        },
        None,
        [h["passage_id"] for h in hits],
    )


# Every not-found path returns this exact string. Three cases used to give three
# different answers, which turned the tool into an oracle: probe order ids and
# item ids, read the wording, and map somebody else's account. The wording now
# reveals nothing about which of the three happened.
NOT_FOUND = "No order found with that reference on this account."


def initiate_return(session: Session, order_id: str = "", item_id: str = "", reason: str = "", **_):
    # Identity and ownership run before any lookup, so a caller learns nothing
    # from the shape of the failure.
    gate = guardrails.check_identity(session, "initiate_return")
    if not gate.permitted:
        return _refusal(gate), gate.as_dict(), []

    order = data.get_order(order_id)
    item = (
        next((i for i in order["items"] if i["item_id"] == item_id), None)
        if order else None
    )
    owned = (
        guardrails.check_ownership(session, order)
        if order else guardrails.Decision(False, "ownership.mismatch", NOT_FOUND)
    )

    # One branch, one string, one rule, whichever of the three went wrong.
    if order is None or item is None or not owned.permitted:
        d = guardrails.Decision(False, "ownership.mismatch", NOT_FOUND)
        return _refusal(d), d.as_dict(), []

    # An idempotency key derived from the request, not from mutated mock state.
    # Without this, a duplicate depends on the in-process dict having been
    # changed, so a restart or a second worker would let the same refund through
    # twice.
    key = f"{session.verified_customer_id}:{order_id}:{item_id}"
    if key in session.completed_returns:
        d = guardrails.Decision(
            False, "return.already_in_progress",
            "A return has already been started for that item.",
        )
        return _refusal(d), d.as_dict(), []

    decision = guardrails.authorise_return(session, order, amount=item["price"])

    if not decision.permitted:
        payload = _refusal(decision)
        # Both value rules mean "not by me", not "never". Without this the model
        # reads refused and tells the customer no, which is wrong and loses them.
        if decision.rule in ("refund.above_auto_cap", "refund.above_session_cap"):
            payload["next_step"] = "escalate_to_human"
            payload["customer_facing_note"] = (
                "This refund needs a colleague to approve it because of the "
                "amount. It can still go ahead."
            )
        return payload, decision.as_dict(), []

    # Mutate the mock store so the duplicate-return guard is real on a second attempt.
    order["return_status"] = "in_progress"
    # Only count money that actually moved. Written here, read by
    # check_refund_value on the next attempt in this conversation.
    session.refunded_so_far += item["price"]
    guardrails.record_refund(session.verified_customer_id, item["price"])
    session.completed_returns.add(key)
    session.actions_taken.append(
        {"action": "initiate_return", "order_id": order_id, "item_id": item_id,
         "reason": reason, "amount": item["price"]}
    )

    return (
        {
            "ok": True,
            "return_reference": f"RET-{order_id.split('-')[1]}-{item_id.split('-')[1]}",
            "item_title": item["title"],
            "refund_amount": item["price"],
            "currency": order["currency"],
            "next_step": "A prepaid Royal Mail return label has been emailed to the customer.",
            "recorded_reason": reason,
        },
        decision.as_dict(),
        [],
    )


def _book_card(book: dict, why: str = ""):
    """One book, as facts. The AI writes the sentence around it."""
    card = {
        "book_id": book["book_id"],
        "title": book["title"],
        "author": book["author"],
        "price": book["price"],
        "blurb": book["blurb"],
        "shop_cat_pick": book["shop_cat_pick"],
    }
    if why:
        card["why"] = why
    return card


def recommend_books(
    session: Session,
    liked_title: str = "",
    mood: str = "",
    themes=None,
    use_purchase_history: bool = False,
    shop_cat_picks_only: bool = False,
    **_,
):
    """
    Suggest books. No permission check, because a bad suggestion costs nothing.

    There is one rule though: every book returned is real and in stock. The AI
    only ever sees titles we sent it, so it cannot suggest something we do not
    sell. It knows thousands of real books and would happily recommend one we
    have never stocked.

    Each suggestion also carries a "why", built from the themes and moods the
    books actually share. A recommendation you cannot explain is not much better
    than a random one.
    """
    themes = themes or []
    already_owned = set()
    seed_books = []
    basis = []

    # Using purchase history means reading their orders, so this needs identity
    # verification even though recommendations normally do not.
    #
    # The risk level follows the DATA being touched, not the name of the tool.
    # Same function, two different risk levels, depending on the arguments.
    if use_purchase_history:
        gate = guardrails.check_identity(session, "find_orders")
        if not gate.permitted:
            return (
                {
                    "ok": False,
                    "refused": True,
                    "rule": gate.rule,
                    "reason": "Cannot use purchase history before verifying the customer.",
                    "instruction": (
                        "You can still recommend without history. Ask what they last enjoyed, "
                        "or what mood they're after."
                    ),
                },
                gate.as_dict(),
                [],
            )
        for order in data.get_orders_for_customer(session.verified_customer_id):
            for item in order["items"]:
                book = catalogue.find_by_title(item["title"])
                if book:
                    already_owned.add(book["book_id"])
                    seed_books.append(book)
        if seed_books:
            basis.append("previous orders")

    if liked_title:
        seed = catalogue.find_by_title(liked_title)
        if seed is None:
            return (
                {
                    "ok": True,
                    "found": False,
                    "recommendations": [],
                    "instruction": (
                        f"'{liked_title}' is not in the catalogue, or the title was ambiguous. "
                        "Ask the customer to confirm the title or describe what they liked "
                        "about it. Do not guess which book they meant."
                    ),
                },
                None,
                [],
            )
        seed_books.append(seed)
        already_owned.add(seed["book_id"])
        basis.append(f"similarity to {seed['title']}")

    pool = catalogue.shop_cat_picks() if shop_cat_picks_only else list(catalogue.CATALOGUE.values())
    pool = [b for b in pool if b["in_stock"] and b["book_id"] not in already_owned]

    results = []

    if seed_books:
        aggregate = {}
        for seed in seed_books:
            for score, book in catalogue.similar_to(seed, limit=6, exclude_ids=already_owned):
                if shop_cat_picks_only and not book["shop_cat_pick"]:
                    continue
                prev = aggregate.get(book["book_id"])
                shared_themes = sorted(set(seed["themes"]) & set(book["themes"]))
                shared_mood = sorted(set(seed["mood"]) & set(book["mood"]))
                reason_bits = []
                if shared_themes:
                    reason_bits.append(", ".join(shared_themes[:2]))
                if shared_mood:
                    reason_bits.append(f"similarly {shared_mood[0]}")
                why = (
                    f"Shares {' and '.join(reason_bits)} with {seed['title']}."
                    if reason_bits
                    else f"Often enjoyed alongside {seed['title']}."
                )
                if prev is None or score > prev[0]:
                    aggregate[book["book_id"]] = (score, book, why)
        ranked = sorted(aggregate.values(), key=lambda t: (-t[0], t[1]["title"]))
        results = [_book_card(b, why) for _, b, why in ranked[:3]]

    elif mood or themes:
        mood_l = (mood or "").strip().lower()
        theme_set = {t.strip().lower() for t in themes}
        scored = []
        for book in pool:
            score = 0.0
            matched = []
            if mood_l and mood_l in [m.lower() for m in book["mood"]]:
                score += 2.0
                matched.append(mood_l)
            hits = theme_set & {t.lower() for t in book["themes"]}
            score += 3.0 * len(hits)
            matched.extend(sorted(hits))
            if score > 0:
                why = f"Matches {', '.join(matched[:2])}."
                scored.append((score, book, why))
        scored.sort(key=lambda t: (-t[0], t[1]["title"]))
        results = [_book_card(b, why) for _, b, why in scored[:3]]
        basis.append("stated mood and themes")

    elif shop_cat_picks_only:
        results = [
            _book_card(b, "On Tiberius's shelf. He does not explain his choices.")
            for b in pool[:3]
        ]
        basis.append("shop cat picks")

    if not results:
        return (
            {
                "ok": True,
                "found": False,
                "recommendations": [],
                "instruction": (
                    "Nothing matched closely enough to recommend honestly. Ask the customer "
                    "what they last enjoyed, or offer Tiberius's staff picks. Do not pad the "
                    "list with books that do not fit."
                ),
            },
            None,
            [],
        )

    return (
        {
            "ok": True,
            "found": True,
            "basis": basis,
            "recommendations": results,
            "instruction": (
                "Recommend only these titles. Mention why each one fits, in your own words. "
                "Two or three is plenty, a long list is a search result, not a recommendation."
            ),
        },
        None,
        [],
    )


def find_book_clubs(session: Session, about_title: str = "", themes=None, **_):
    """
    Find a reading group. Real groups only, with their real meeting dates and
    member counts. If nothing matches we say so, because a made-up club with a
    made-up date is worse than no answer.
    """
    themes = themes or []
    clubs = []

    if about_title:
        book = catalogue.find_by_title(about_title)
        if book is None:
            return (
                {
                    "ok": True,
                    "found": False,
                    "clubs": [],
                    "instruction": (
                        f"'{about_title}' is not in the catalogue, so there is no club for it. "
                        "Ask the customer to confirm the title. Do not invent a club, a meeting "
                        "date or a member count, and do not confirm a club a customer describes "
                        "unless this tool returned it."
                    ),
                },
                None,
                [],
            )
        clubs = catalogue.clubs_for_book(book)
    elif themes:
        theme_set = {t.strip().lower() for t in themes}
        scored = []
        for club in catalogue.BOOK_CLUBS.values():
            overlap = len(theme_set & {t.lower() for t in club["themes"]})
            if overlap:
                scored.append((overlap, club))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
        clubs = [c for _, c in scored[:2]]

    if not clubs:
        return (
            {
                "ok": True,
                "found": False,
                "clubs": [],
                "instruction": "No club matched. Do not invent one. Offer recommendations instead.",
            },
            None,
            [],
        )

    return (
        {
            "ok": True,
            "found": True,
            "clubs": [
                {
                    "club_id": c["club_id"],
                    "name": c["name"],
                    "currently_reading": catalogue.CATALOGUE[c["current_book_id"]]["title"],
                    "next_meeting": c["next_meeting"],
                    "members": c["members"],
                    "format": c["format"],
                    "description": c["description"],
                }
                for c in clubs
            ],
            "instruction": (
                "Mention at most two, with the real meeting date and member count. A specific "
                "invitation lands; a general one does not."
            ),
        },
        None,
        [],
    )


def escalate_to_human(session: Session, reason: str = "", summary: str = "", **_):
    session.escalated = True
    return (
        {
            "ok": True,
            "queued": True,
            "queue": "bookly-support-tier1",
            "handoff_reason": reason,
            "context_passed": summary,
            "expected_wait_minutes": 4,
        },
        None,
        [],
    )


HANDLERS = {
    "verify_customer": verify_customer,
    "recommend_books": recommend_books,
    "find_book_clubs": find_book_clubs,
    "find_orders": find_orders,
    "get_order": get_order,
    "search_policy": search_policy,
    "initiate_return": initiate_return,
    "escalate_to_human": escalate_to_human,
}
