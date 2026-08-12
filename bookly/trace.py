"""
Structured tracing.

Every turn records what the model decided, which tools it called, which
guardrails fired, which passages it cited, and how the turn ended.

Not debug logging. This is the substrate for three things a production deployment
needs: evaluation, since you cannot score behaviour you cannot inspect; quality
monitoring by sampling live conversations; and answering "why did it do that",
which in a regulated buyer's procurement is the question that closes the deal.

JSON lines, so it loads straight into a dataframe or a warehouse table.
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
    tool_name: str
    arguments: dict
    guardrail: Optional[dict] = None
    outcome: str = "ok"  # ok | refused | error
    result_summary: Optional[str] = None
    cited_passages: list = field(default_factory=list)


@dataclass
class TurnTrace:
    """One customer message and everything that followed."""

    turn_id: str
    conversation_id: str
    timestamp: str
    customer_message: str
    model_stops: int = 0                       # how many round trips the loop took
    tool_events: list = field(default_factory=list)
    guardrails_fired: list = field(default_factory=list)
    cited_passages: list = field(default_factory=list)
    # Constraints the model was told about, as opposed to constraints that had
    # to be enforced. A well-behaved agent reads the first and never triggers the
    # second. Tracking them separately distinguishes "the model declined" from
    # "the code caught the model".
    constraints_surfaced: list = field(default_factory=list)
    resolution: str = "answered"  # answered | acted | refused | clarifying | escalated | recommended
    identity_verified: bool = False
    # Set when the agent offered something useful after a refusal or dead end.
    # Separate from `resolution` because a refusal that ends well and one that
    # ends badly look identical on a containment metric, and the gap between them
    # is the commercial argument.
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

    # Conversation rollup. The fields a CX operations team would put on a
    # dashboard, derived rather than hand-counted.

    def summary(self) -> dict:
        resolutions = [t.resolution for t in self.turns]
        return {
            "conversation_id": self.conversation_id,
            "turns": len(self.turns),
            "tool_calls": sum(len(t.tool_events) for t in self.turns),
            "guardrails_fired": [r for t in self.turns for r in t.guardrails_fired],
            "constraints_surfaced": sorted({c for t in self.turns for c in t.constraints_surfaced}),
            # The interesting split. "model_declined" means the agent was told
            # a constraint and respected it unprompted. "code_blocked" means it
            # attempted the action and was stopped. Both are safe. The ratio
            # tells you how often the model needs catching, which is what should
            # shape investment in the control layer.
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
            # The metric separating a returns desk from a concierge. Of the
            # turns that ended in a refusal, how many gave the customer somewhere
            # to go?
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
