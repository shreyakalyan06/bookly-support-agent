# Bookly support agent

A support agent for a fictional online bookshop. Python, calling the Anthropic API
directly, no agent framework.

Two support jobs end to end: where is my order, and I want to send this back,
refund included. It also answers policy questions and suggests a book after
declining a return.

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python cli.py --trace                        # chat, with the tool calls shown
python evals/test_control_layer.py           # 37 checks, no API key needed
python evals/run_scenarios.py --repeats 3    # 14 conversations, needs a key
```

| Customer | Credentials | Orders |
|---|---|---|
| Priya Raman | `priya.raman@example.com` / `SW1A 1AA` | `ORD-84201` returnable · `ORD-84315` in transit · `ORD-79930` delivered 104 days ago |
| Tom Whitfield | `tom.whitfield@example.com` / `M1 4BT` | `ORD-84420` £342, over the cap · `ORD-84501` return already running |

Priya holds two open orders, so "where is my order" has no single answer and the
agent has to ask.

## The design

Finishing the job means moving a customer's money. A limit written in a prompt
moves when a customer pushes, so the limits live in code.

The model picks what to attempt. `guardrails.py` decides whether it is allowed.
That file imports nothing to do with the model and never reads the conversation,
so no wording a customer chooses changes its answer.

`agent.py` checks `guardrails.TOOL_POLICY` before calling any handler. A tool
absent from that table is refused, so a new tool fails closed. A test walks both
tables and fails on any mismatch.

Actions are sorted by one question: if this goes wrong, does it reverse?

| Tier | Actions | Gate | Cost of an error |
|---|---|---|---|
| 0 | policy lookup, recommendations | none | a correction |
| 1 | order list, order detail | identity verified | another customer's data |
| 2 | returns and refunds | four checks, £100 cap | money, and it does not come back |

Closing the refund path is what lets tier 0 stay open. There is deliberately no
check on recommendations, and a comment in `guardrails.py` says why.

```
agent.py       the loop, hand-rolled tool calling, 8 rounds maximum
tools.py       7 tool schemas and their handlers
guardrails.py  the permission checks. No model imports.
trace.py       every decision recorded as JSON lines
data.py        customers, orders, 9 policy passages
catalogue.py   15 books, similarity by theme and mood
policy.py      keyword retrieval with a relevance cutoff
```

## Three decisions and what they cost

**Refund rules live in code, not in the model's instructions.** Costs flexibility:
a fair exception gets blocked and needs a person. Worth it because a refund does
not come back, and 37 offline checks prove the limits hold without spending
anything on the API.

**The agent quotes policy only after retrieving it, and cites the passage.**
Deflection drops and resolved-correctly rises, so you pick which one you report.
Worth it because without a cutoff there is always a least bad match, and a gift
card passage will confidently answer a question about loyalty points.

**An unclear request gets a question, never a guess.** Costs one extra message.
Worth it because guessing right usually means cancelling the wrong order sometimes.

Two smaller ones. Chat rather than voice, because voice spends the budget on
latency and speech handling rather than on the permission design. Recommendations
are weighted arithmetic on theme and mood rather than a second model call, so they
are free, repeatable, and every suggestion carries a reason.

## Testing

The permission layer gets 37 plain assertions and no API key, because none of it
touches the model. The conversations get 13 scenarios, six of them attacks.
Assertions read the trace rather than the wording of the reply, because the
wording changes every run and the trace does not.

`test_eval_suite.py` is a negative control. Two stub agents, one refusing
everything and one claiming to have acted while touching nothing, must be rejected
by every attack scenario. When I first ran it, five passed the do-nothing stub:
they checked that nothing bad happened without checking anything happened at all.

The recovery offer is not asserted anywhere, because nothing enforces it. It
appeared in one run of three. That is the argument for moving it into code rather
than a reason to loosen a test.

Assertions of mine failed a correct agent eight times and had to change. Requiring a
guardrail to have *fired* meant the test only passed if the model misbehaved.
Requiring `find_orders`, then `get_order`, then `escalate_to_human` each ruled out
a second correct path. Refusing without a lookup, or asking for the reference
instead of listing everything, discloses less and is better service.
Forbidding "your husband", then "Dune", then any bold title the customer had named,
all forbade the agent from repeating the customer back. Two rules came out of that. A forbidden string must be one the agent could only
know from the data. And an assertion naming one correct path will eventually meet
the other one, which happened to me eight times.

Results in `evals/results/`.

## Known limits

Identity is email plus postcode, which is weak. A real deployment uses the
customer's existing login.

The £100 cap is a constant. It belongs in a settings service a support manager
owns, still resolved outside the model.

The trace records messages verbatim, so emails and postcodes land in it in clear.
Production needs hashed identifiers and a retention window.

The refund cap is per decision, not per customer. Four separate £75 refunds each
pass it. A rolling total keyed by customer closes that, and needs a store that
outlives a conversation.

English only, UK only. No memory between conversations.

## What I would change first

Move what the prompt currently guards into code. The agent names only stocked books
and offers an alternative after a refusal. Both hold today, and so did the refund
instruction. I trust the refund rule because `guardrails.py` enforces it.

Then replay real conversations rather than my thirteen invented ones, since eight
of my assertions were wrong. Then the per-customer refund total. Then gate releases on the
attack score.

All of that before new capability. Behaviour varies between runs, so without
measurement you cannot tell a change from an improvement.
