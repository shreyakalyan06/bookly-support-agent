"""
Agent orchestration.

A hand-written tool-use loop against the Anthropic Messages API. No framework, on
purpose. The loop is about fifteen lines of real logic, and owning it keeps the
interesting decisions visible: when to stop, what to do with a refusal, what gets
logged.

    send conversation + tool schemas
      -> model returns text and/or tool_use blocks
      -> tool_use: run each handler, append tool_result blocks, send again
      -> no tool_use: the turn is done

A hard iteration cap stops a confused model looping at the customer's expense.
"""

import json
import os
from typing import Optional

from anthropic import Anthropic

from .guardrails import Session
from .tools import HANDLERS, TOOL_SCHEMAS
from .trace import ToolEvent, Tracer

MODEL = os.environ.get("BOOKLY_MODEL", "claude-sonnet-5")

# verify -> find -> get -> act is four round trips. Eight leaves headroom for a
# retry without allowing an unbounded loop.
MAX_ITERATIONS = 8


SYSTEM_PROMPT = """You are the Bookly customer support assistant. Bookly is an online bookstore in the UK.

Your job is to resolve the customer's problem, not to describe how they could resolve it themselves.

## How you work

You have tools. Use them. Specifically:

- You cannot see any customer or order information unless you retrieve it with a tool. You have no memory of previous conversations and no general knowledge about this customer.
- Before you touch any order data you must verify the customer with `verify_customer`, using their email address and billing postcode. Ask for both. Never invent, guess or partially accept these.
- Before you state any Bookly policy -- delivery times, return windows, refund timing, cancellations, gift cards, password resets -- you must call `search_policy` and answer only from what it returns. Cite the passage id in square brackets, like [POL-RET-01].
- If `search_policy` returns nothing, say you do not have that information and offer to pass the customer to a colleague. Do not fill the gap from general knowledge.

## When to ask instead of act

Ask a clarifying question rather than choosing for the customer when:

- They refer to "my order" and more than one order could plausibly match.
- They want to return something and the order has more than one item.
- Anything about their request is ambiguous in a way that would make an action hard to undo.

One extra question costs the customer a few seconds. Acting on the wrong order costs them their trust.

## When a tool refuses

Some tools will return `refused: true` with a rule and a reason. This is normal and correct -- it means the action is not permitted. When it happens:

- Tell the customer plainly what the position is, in your own words, without jargon or rule names.
- Never retry the same call hoping for a different answer, and never work around it with a different tool.
- If the customer still needs the outcome, use `escalate_to_human` with a summary so they do not have to start again.

You do not have the authority to make exceptions to these refusals. Do not imply that you might.

## Don't stop at resolved

Bookly is a bookshop with a reading community, not a returns desk. When you have dealt with what the customer came for, consider whether there is a genuinely useful next thing — and offer it once, briefly, never twice.

This matters most when you have had to say no. A refusal that ends the conversation costs Bookly a customer. A refusal followed by something actually useful often does not.

So: if you refuse a return because the window has closed, that customer still has a book they didn't get on with. Offer something they might prefer, or a group discussing that book. If someone is returning a book because it wasn't what they expected, find out what they were hoping for. If a delivery is late, the wait is more bearable with something to look forward to.

Use `recommend_books` and `find_book_clubs` for this. You may only mention titles and clubs those tools return. Never invent a book, a club, a meeting date or a member count — a recommendation for something Bookly cannot sell creates a support ticket instead of closing one.

Read the room. A furious customer wants their problem fixed and nothing else. Someone browsing is glad of a suggestion. If in doubt, resolve the problem and stop.

## Tone

Warm, direct, and brief. Short paragraphs. No corporate padding, no "I understand your frustration". British English. Do not open with an apology unless something actually went wrong. Do not use bullet lists unless you are laying out genuine options.

Never mention tools, rules, systems, passage lookups or internal mechanics to the customer. Cite passage ids and nothing else about how you work.
"""


class BooklyAgent:
    def __init__(self, api_key: Optional[str] = None, trace_path: Optional[str] = "traces/session.jsonl"):
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.session = Session()
        self.tracer = Tracer(path=trace_path)
        self.messages: list[dict] = []

    # Resolution classification, derived from what happened rather than from
    # asking the model to self-report. Self-reporting fails in exactly the cases
    # that matter most.
    @staticmethod
    def _classify(turn, agent_text: str) -> str:
        tools_used = [e.tool_name for e in turn.tool_events]

        if "escalate_to_human" in tools_used:
            return "escalated"
        if any(e.outcome == "refused" for e in turn.tool_events):
            return "refused"
        if any(e.tool_name == "initiate_return" and e.outcome == "ok" for e in turn.tool_events):
            return "acted"
        # "recommended" applies only when recommending was the request.
        #
        # v1 returned it whenever those tools ran, so a correct refusal followed
        # by a helpful suggestion got reclassified from "refused" to
        # "recommended". The supplementary outcome overwrote the primary one, and
        # scenarios written before the concierge feature started failing for
        # behaviour I had asked for.
        #
        # `recovery_offered` already tracks the offer, so it does not need to
        # compete for this field.
        support_tools = {"find_orders", "get_order", "search_policy", "initiate_return"}
        used_support = any(e.tool_name in support_tools for e in turn.tool_events)
        if not used_support and any(
            e.tool_name in {"recommend_books", "find_book_clubs"} and e.outcome == "ok"
            for e in turn.tool_events
        ):
            return "recommended"
        # "Clarifying" means the agent could not proceed and needs input, not
        # that its reply contains a question mark.
        #
        # Three attempts, which is the point. v1 checked for a trailing '?' and
        # misfiled any reply that asked something then closed politely. v2
        # checked anywhere and immediately misfiled every courtesy closer, so the
        # fix introduced a new failure.
        #
        # v3 reads the trace instead of the prose. If a substantive tool returned
        # a result the agent made progress, and a question is a courtesy. Only
        # when nothing advanced and it asked something is it genuinely blocked.
        #
        # Derive metrics from what the system did, not what it said. Surface text
        # is the least reliable signal available.
        SUBSTANTIVE = {
            "find_orders",
            "get_order",
            "search_policy",
            "recommend_books",
            "find_book_clubs",
        }
        made_progress = any(
            e.tool_name in SUBSTANTIVE and e.outcome == "ok" for e in turn.tool_events
        )

        if not made_progress and "?" in agent_text:
            return "clarifying"
        return "answered"

    def _run_tool(self, turn, name: str, arguments: dict):
        handler = HANDLERS.get(name)
        if handler is None:
            payload = {"ok": False, "reason": f"Unknown tool {name}."}
            self.tracer.record_tool(
                turn, ToolEvent(tool_name=name, arguments=arguments, outcome="error")
            )
            return payload

        try:
            payload, guardrail, cited = handler(self.session, **arguments)
        except Exception as exc:  # noqa: BLE001
            # A tool failure is a normal, describable outcome. Tell the model
            # plainly so it apologises and escalates rather than inventing a
            # result.
            payload = {
                "ok": False,
                "error": True,
                "reason": f"The system could not complete that request: {exc}",
                "instruction": "Tell the customer there was a technical problem and offer a human.",
            }
            guardrail, cited = None, []

        outcome = "ok"
        if payload.get("error"):
            outcome = "error"
        elif payload.get("refused"):
            outcome = "refused"

        # Told about, not enforced. Recorded separately from guardrails_fired.
        elig = payload.get("return_eligibility") or {}
        if elig.get("surfaced_constraint"):
            self.tracer.record_constraint(turn, elig["surfaced_constraint"])
        if payload.get("found") is False:
            self.tracer.record_constraint(turn, f"{name}.no_match")
        if name == "verify_customer" and payload.get("verified") is False:
            self.tracer.record_constraint(turn, "identity.not_yet_verified")

        self.tracer.record_tool(
            turn,
            ToolEvent(
                tool_name=name,
                arguments=arguments,
                guardrail=guardrail,
                outcome=outcome,
                result_summary=payload.get("reason") or ("ok" if payload.get("ok") else None),
                cited_passages=cited,
            ),
        )
        return payload

    def send(self, customer_message: str) -> str:
        """Process one customer message and return the agent's reply."""
        turn = self.tracer.start_turn(customer_message)
        self.messages.append({"role": "user", "content": customer_message})

        final_text = ""

        for _ in range(MAX_ITERATIONS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=self.messages,
            )
            turn.model_stops += 1

            text_blocks = [b.text for b in response.content if b.type == "text"]
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            self.messages.append({"role": "assistant", "content": response.content})

            if not tool_uses:
                final_text = "\n".join(text_blocks).strip()
                break

            results = []
            for block in tool_uses:
                payload = self._run_tool(turn, block.name, dict(block.input))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(payload),
                    }
                )
            self.messages.append({"role": "user", "content": results})
        else:
            # Loop cap hit. Fail visibly rather than returning nothing.
            final_text = (
                "I'm having trouble getting to the bottom of this. Let me pass you to a "
                "colleague who can help."
            )
            self._run_tool(
                turn,
                "escalate_to_human",
                {"reason": "iteration_cap_reached", "summary": customer_message},
            )

        tools_used = {e.tool_name for e in turn.tool_events if e.outcome == "ok"}
        recovery = bool(tools_used & {"recommend_books", "find_book_clubs"})

        self.tracer.end_turn(
            turn,
            agent_message=final_text,
            resolution=self._classify(turn, final_text),
            identity_verified=self.session.verified_customer_id is not None,
            recovery_offered=recovery,
        )
        return final_text
