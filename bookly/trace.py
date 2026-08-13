"""
The record of what happened.

The AI does not say the same thing twice. Ask it the same question tomorrow and
the wording will be different, even when the behaviour is identical. So we
cannot test it by comparing its replies to expected text.

What does stay the same is what it DID. Did it check identity before reading the
order? Did it look up the policy before quoting it? Did the refund get blocked?
Those are facts, and they are the same every run.

This file records those facts. The tests then check the record rather than the
wording, which is why they still pass when the AI phrases things differently.

Written as JSON Lines (one JSON object per line). That format lets us append a
line without rewriting the file, and load the whole thing into a spreadsheet or
a database table without any parsing.
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolEvent:
    """One tool the AI asked for, and what happened when we ran it."""
    tool_name: str
    arguments: dict
    guardrail: Optional[dict] = None
    outcome: str = "ok"  # ok | refused | error
    result_summary: Optional[str] = None
    cited_passages: list = field(default_factory=list)


@dataclass
class TurnTrace:
    """One customer message, and everything that happened because of it."""

    turn_id: str
    conversation_id: str
    timestamp: str
    customer_message: str
    model_stops: int = 0                       # how many round trips the loop took
    # Cost and latency, measured rather than estimated. evals/value_case.py reads
    # these, so any figure quoted has a source in the record.
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    tool_events: list = field(default_factory=list)
    guardrails_fired: list = field(default_factory=list)
    cited_passages: list = field(default_factory=list)
    # Limits the AI was TOLD about, as opposed to limits that had to STOP it.
    #
    # Two different things, and worth separating. If we tell the AI an order is
    # 104 days old, a well-behaved one never even asks for the refund. Nothing
    # gets blocked because nothing was attempted.
    #
    # A guardrail firing means the AI tried something it should not have. So
    # counting these separately tells us how often it needed catching.
    constraints_surfaced: list = field(default_factory=list)
    resolution: str = "answered"  # answered | acted | refused | clarifying | escalated | recommended
    identity_verified: bool = False
    # Did the agent offer the customer something after saying no?
    #
    # Kept as its own field for a reason. Two conversations both refuse a
    # return. One customer leaves annoyed; the other gets two book suggestions
    # they might prefer. On a "handled without a human" metric those
    # look identical. One lost you a customer and one did not.
    recovery_offered: bool = False
    agent_message: str = ""

    def as_dict(self):
        d = asdict(self)
        d["tool_events"] = [asdict(e) if not isinstance(e, dict) else e for e in self.tool_events]
        return d


class Tracer:
    def __init__(self, path: Optional[str] = "traces/session.jsonl", conversation_id: Optional[str] = None):
        self.conversation_id = conversation_id or uuid.uuid4().hex[:12]
        self.turns: list[TurnTrace] = []
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def start_turn(self, customer_message: str) -> TurnTrace:
        turn = TurnTrace(
            turn_id=uuid.uuid4().hex[:8],
            conversation_id=self.conversation_id,
            timestamp=_now(),
            customer_message=customer_message,
        )
        self.turns.append(turn)
        return turn

    def record_constraint(self, turn: TurnTrace, rule: str):
        if rule not in turn.constraints_surfaced:
            turn.constraints_surfaced.append(rule)

    def record_tool(self, turn: TurnTrace, event: ToolEvent):
        turn.tool_events.append(event)
        if event.guardrail and not event.guardrail.get("permitted", True):
            turn.guardrails_fired.append(event.guardrail["rule"])
        for pid in event.cited_passages:
            if pid not in turn.cited_passages:
                turn.cited_passages.append(pid)

    def end_turn(
        self,
        turn: TurnTrace,
        agent_message: str,
        resolution: str,
        identity_verified: bool,
        recovery_offered: bool = False,
    ):
        turn.agent_message = agent_message
        turn.resolution = resolution
        turn.identity_verified = identity_verified
        turn.recovery_offered = recovery_offered
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(turn.as_dict()) + "\n")

    # Totals for the whole conversation. These are the numbers a support team
    # would actually put on a dashboard, worked out from the record rather than
    # counted by hand.

    def summary(self) -> dict:
        resolutions = [t.resolution for t in self.turns]
        return {
            "conversation_id": self.conversation_id,
            "turns": len(self.turns),
            "tool_calls": sum(len(t.tool_events) for t in self.turns),
            "input_tokens": sum(t.input_tokens for t in self.turns),
            "output_tokens": sum(t.output_tokens for t in self.turns),
            "seconds": round(sum(t.seconds for t in self.turns), 1),
            "guardrails_fired": [r for t in self.turns for r in t.guardrails_fired],
            "constraints_surfaced": sorted({c for t in self.turns for c in t.constraints_surfaced}),
            # How did the rule hold?
            #
            #   model_declined  we told the AI the limit and it respected it
            #   code_blocked    the AI tried anyway and we stopped it
            #
            # Both are safe. The first is nicer, because the customer gets a
            # clean explanation instead of watching the system catch itself.
            # The ratio tells you how often the AI needs catching, which is what
            # should decide how much effort goes into the checks.
            "refusal_source": (
                "code_blocked"
                if any(t.guardrails_fired for t in self.turns)
                else (
                    "model_declined"
                    if any(t.constraints_surfaced for t in self.turns)
                    else "none"
                )
            ),
            "passages_cited": sorted({p for t in self.turns for p in t.cited_passages}),
            "actions_taken": resolutions.count("acted"),
            "refusals": resolutions.count("refused"),
            "clarifying_questions": resolutions.count("clarifying"),
            "escalated": "escalated" in resolutions,
            "contained": "escalated" not in resolutions,
            # Of the times we said no, how often did we still give the
            # customer somewhere to go? This is the number that separates a
            # returns desk from something people want to come back to.
            "refusals_with_recovery": sum(
                1 for t in self.turns if t.resolution == "refused" and t.recovery_offered
            ),
            "recovery_rate_on_refusals": (
                round(
                    sum(1 for t in self.turns if t.resolution == "refused" and t.recovery_offered)
                    / max(resolutions.count("refused"), 1),
                    2,
                )
                if resolutions.count("refused")
                else None
            ),
        }
