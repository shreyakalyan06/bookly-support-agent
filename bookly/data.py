"""
Mock data store for Bookly.

In production this becomes real system calls: an order management system, a CRM
record, a help centre. What matters is that data lives only here and every tool
reads through it. Nothing reaches the model except as a tool return value.

Dates are relative to today so the demo behaves the same whenever it runs.
"""

from datetime import date, timedelta

TODAY = date.today()


def _days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


# Customers. Email plus postcode is deliberately weak verification, but it is
# structurally enforced. See guardrails.py. Real deployments would use existing
# account auth or step-up verification.

CUSTOMERS = {
    "CUST-1001": {
        "customer_id": "CUST-1001",
        "name": "Priya Raman",
        "email": "priya.raman@example.com",
        "postcode": "SW1A 1AA",
    },
    "CUST-1002": {
        "customer_id": "CUST-1002",
        "name": "Tom Whitfield",
        "email": "tom.whitfield@example.com",
        "postcode": "M1 4BT",
    },
}


# Orders, chosen to force specific behaviours:
#   ORD-84201  delivered 6 days ago       inside return window, low value
#   ORD-84315  in transit                 not returnable yet
#   ORD-79930  delivered 104 days ago     outside return window
#   ORD-84420  delivered, GBP 342.00      above auto-refund cap
#   ORD-84501  return already in progress duplicate-refund guard
#
# CUST-1001 has two open orders, so "where is my order" forces a question.

_ORDER_FIXTURES = {
    "ORD-84201": {
        "order_id": "ORD-84201",
        "customer_id": "CUST-1001",
        "status": "delivered",
        "placed_date": _days_ago(11),
        "delivered_date": _days_ago(6),
        "currency": "GBP",
        "total": 24.98,
        "carrier": "Royal Mail",
        "tracking": "RM418820291GB",
        "items": [
            {"item_id": "ITM-1", "title": "The Fifth Season", "qty": 1, "price": 9.99},
            {"item_id": "ITM-2", "title": "Piranesi", "qty": 1, "price": 14.99},
        ],
        "return_status": None,
    },
    "ORD-84315": {
        "order_id": "ORD-84315",
        "customer_id": "CUST-1001",
        "status": "in_transit",
        "placed_date": _days_ago(3),
        "delivered_date": None,
        "expected_delivery": (TODAY + timedelta(days=2)).isoformat(),
        "currency": "GBP",
        "total": 18.50,
        "carrier": "Evri",
        "tracking": "EV92014477",
        "items": [
            {"item_id": "ITM-1", "title": "Babel", "qty": 1, "price": 18.50},
        ],
        "return_status": None,
    },
    "ORD-79930": {
        "order_id": "ORD-79930",
        "customer_id": "CUST-1001",
        "status": "delivered",
        "placed_date": _days_ago(110),
        "delivered_date": _days_ago(104),
        "currency": "GBP",
        "total": 31.00,
        "carrier": "Royal Mail",
        "tracking": "RM118820104GB",
        "items": [
            {"item_id": "ITM-1", "title": "Sea of Tranquility", "qty": 1, "price": 16.00},
            {"item_id": "ITM-2", "title": "Klara and the Sun", "qty": 1, "price": 15.00},
        ],
        "return_status": None,
    },
    "ORD-84420": {
        "order_id": "ORD-84420",
        "customer_id": "CUST-1002",
        "status": "delivered",
        "placed_date": _days_ago(9),
        "delivered_date": _days_ago(4),
        "currency": "GBP",
        "total": 342.00,
        "carrier": "DPD",
        "tracking": "DPD7741200",
        "items": [
            {
                "item_id": "ITM-1",
                "title": "The Complete Works of Ursula K. Le Guin (Collector's Edition)",
                "qty": 1,
                "price": 342.00,
            },
        ],
        "return_status": None,
    },
    "ORD-84501": {
        "order_id": "ORD-84501",
        "customer_id": "CUST-1002",
        "status": "delivered",
        "placed_date": _days_ago(14),
        "delivered_date": _days_ago(8),
        "currency": "GBP",
        "total": 22.00,
        "carrier": "Royal Mail",
        "tracking": "RM418820777GB",
        "items": [
            {"item_id": "ITM-1", "title": "Tomorrow, and Tomorrow, and Tomorrow", "qty": 1, "price": 22.00},
        ],
        "return_status": "in_progress",
    },
}


# Policy corpus. Each passage has a stable id, and the agent must cite one for
# any policy claim. That is what makes grounding auditable rather than
# aspirational.

POLICY_PASSAGES = [
    {
        "id": "POL-RET-01",
        "title": "Returns window",
        "text": (
            "Bookly accepts returns on physical books within 30 days of the delivery date. "
            "Items must be in resaleable condition. Returns cannot be started before an "
            "order has been delivered."
        ),
        "keywords": ["return", "returns", "send back", "30 days", "window", "resaleable", "refund eligibility"],
    },
    {
        "id": "POL-RET-02",
        "title": "Return postage",
        "text": (
            "Return postage is free for orders delivered within the United Kingdom. "
            "Customers outside the UK are responsible for return postage costs unless the "
            "item arrived damaged or the wrong item was sent."
        ),
        "keywords": ["postage", "return cost", "who pays", "shipping back", "free returns", "international return"],
    },
    {
        "id": "POL-REF-01",
        "title": "Refund timing",
        "text": (
            "Refunds are issued to the original payment method once the returned item is "
            "received at our warehouse. Card refunds typically appear within 5 to 7 working "
            "days of processing."
        ),
        "keywords": ["refund", "money back", "how long", "payment method", "working days", "when will i get"],
    },
    {
        "id": "POL-REF-02",
        "title": "Damaged or incorrect items",
        "text": (
            "If an item arrives damaged or is not the item ordered, Bookly will arrange a "
            "replacement or a full refund including postage. Photographic evidence may be "
            "requested. These cases are not subject to the standard 30 day window."
        ),
        "keywords": ["damaged", "broken", "wrong item", "incorrect", "replacement", "torn", "faulty"],
    },
    {
        "id": "POL-SHIP-01",
        "title": "UK delivery times",
        "text": (
            "Standard UK delivery takes 3 to 5 working days. Express UK delivery is next "
            "working day when ordered before 2pm. Delivery estimates exclude weekends and "
            "public holidays."
        ),
        "keywords": ["delivery time", "how long shipping", "standard delivery", "express", "next day", "uk delivery"],
    },
    {
        "id": "POL-SHIP-02",
        "title": "International delivery",
        "text": (
            "Bookly ships to the EU, United States, Canada and Australia. International "
            "delivery takes 7 to 21 working days. Customers are responsible for any import "
            "duties or taxes charged by the destination country."
        ),
        "keywords": ["international", "overseas", "abroad", "eu", "customs", "duties", "import tax", "ship to"],
    },
    {
        "id": "POL-ACC-01",
        "title": "Password reset",
        "text": (
            "Customers can reset their password from the sign-in page using the 'Forgotten "
            "password' link. A reset email is sent to the address on the account and the "
            "link is valid for 60 minutes. Bookly support cannot set or view passwords."
        ),
        "keywords": ["password", "reset", "log in", "login", "cannot sign in", "locked out", "forgotten"],
    },
    {
        "id": "POL-ACC-02",
        "title": "Order cancellation",
        "text": (
            "Orders can be cancelled free of charge until they are dispatched. Once an order "
            "has been dispatched it must be handled as a return after delivery."
        ),
        "keywords": ["cancel", "cancellation", "stop order", "change my mind before"],
    },
    {
        "id": "POL-GIFT-01",
        "title": "Gift cards",
        "text": (
            "Bookly gift cards do not expire and cannot be exchanged for cash. Gift card "
            "balances are non-refundable once redeemed against an order."
        ),
        "keywords": ["gift card", "voucher", "credit", "balance", "expire"],
    },
]


def get_customer_by_email(email: str):
    email = (email or "").strip().lower()
    for c in CUSTOMERS.values():
        if c["email"].lower() == email:
            return c
    return None


def get_orders_for_customer(customer_id: str):
    return [o for o in ORDERS.values() if o["customer_id"] == customer_id]


def get_order(order_id: str):
    return ORDERS.get((order_id or "").strip().upper())


# Per-thread order state.
#
# initiate_return sets return_status so a second attempt is genuinely blocked.
# Correct behaviour, but it makes the store stateful, and the eval runner runs
# scenarios concurrently in one process.
#
# Symptom: return-eligible-end-to-end passed exactly 1 of 3 runs, reason
# "already in progress". Run one succeeded, mutated the shared dict, poisoned
# the other two. A harness defect that looked like an agent failure.
#
# Each thread now gets its own deep copy. In production this layer is a database
# and the equivalent is a transaction rolled back per test.

import copy
import threading

_local = threading.local()


def _orders() -> dict:
    if not hasattr(_local, "orders"):
        _local.orders = copy.deepcopy(_ORDER_FIXTURES)
    return _local.orders


def reset_state():
    """Restore pristine order data for the current thread."""
    _local.orders = copy.deepcopy(_ORDER_FIXTURES)


class _OrderStore:
    """Dict-like view onto this thread's orders, so `ORDERS[...]` still works."""

    def __getitem__(self, key):
        return _orders()[key]

    def __setitem__(self, key, value):
        _orders()[key] = value

    def __contains__(self, key):
        return key in _orders()

    def get(self, key, default=None):
        return _orders().get(key, default)

    def values(self):
        return _orders().values()

    def items(self):
        return _orders().items()

    def keys(self):
        return _orders().keys()

    def __iter__(self):
        return iter(_orders())

    def __len__(self):
        return len(_orders())


ORDERS = _OrderStore()
