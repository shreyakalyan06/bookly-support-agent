# Bookly support agent

A customer support agent for a fictional online bookshop. Python, calling the
Anthropic API directly, no agent framework.

It handles two jobs end to end: where is my order, and I want to send this back,
refund included. It also answers policy questions, suggests books, and hands over
to a person.

---

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python cli.py --trace                        # chat, with the tool calls shown
./verify.sh                                  # every offline check, no key needed
./verify.sh --full                           # regenerates every number first
```

No API key? Read [`evals/results/sample-transcript.txt`](evals/results/sample-transcript.txt).
Two real conversations with the tool calls and permission decisions shown.

| Customer | Credentials | Orders |
|---|---|---|
| Priya Raman | `priya.raman@example.com` / `SW1A 1AA` | `ORD-84201` returnable · `ORD-84315` in transit · `ORD-79930` delivered 104 days ago |
| Tom Whitfield | `tom.whitfield@example.com` / `M1 4BT` | `ORD-84420` £342, over the cap · `ORD-84501` return already running |

Priya holds two open orders, so "where is my order" has no single answer and the
agent has to ask.

---

## The design

Finishing the job means moving a customer's money. Prompts do not hold under
pressure, so the limits live in code.

The model picks what to attempt. `guardrails.py` decides whether it is allowed.
That file imports nothing to do with the AI and never reads the conversation, so
no wording a customer chooses changes its answer.

`agent.py` checks `guardrails.TOOL_POLICY` before calling any handler. A tool
absent from that table is refused, so a new tool fails closed. A test walks
`HANDLERS` both ways and fails on any name missing from either side.

Actions are sorted by whether a mistake reverses.

| Tier | Actions | Gate | Cost of an error |
|---|---|---|---|
| 0 | policy lookup, recommendations, book clubs | none | a correction |
| 1 | order list, order detail | identity verified | another customer's data |
| 2 | returns and refunds | four checks, £100 per refund, £150 rolling | money, and it does not come back |

Closing the refund path is what lets tier 0 stay open.

```
agent.py       the loop, hand-rolled tool calling, 8 rounds maximum
tools.py       8 tool schemas and their handlers
guardrails.py  the permission checks. No AI imports.
trace.py       every decision, plus tokens and seconds, as JSON lines
data.py        orders and customers    catalogue.py  books and clubs
policy.py      9 policy passages, retrieval with citations
```

---

## Three decisions and what they cost

**Money rules live in code, not in the AI's instructions.** Costs flexibility. A
fair exception gets blocked and needs a person. Worth it because a refund never
comes back, and a limit written in a prompt moves when a customer pushes.

**The agent quotes policy only after retrieving it, and cites the passage.**
Deflection drops and resolved-correctly rises, so you pick which one you report.
Worth it because without a relevance cutoff there is always a least bad match, and
a gift card passage will confidently answer a question about loyalty points.

**An unclear request gets a question, never a guess.** Costs one extra message.
Worth it because guessing right usually means cancelling the wrong order
sometimes.

Two more, briefly. Chat rather than voice, because voice spends the budget on
latency and speech handling. Recommendations are weighted arithmetic on theme and
mood rather than a second model call, so they are free, repeatable, and every
suggestion carries a reason.

---

## Testing

Three suites. `./verify.sh` runs all three.

```bash
python evals/test_control_layer.py    # 75 assertions, no API key
python evals/test_eval_suite.py       # proves the suite can fail, no API key
python evals/run_scenarios.py --repeats 3
```

**The permission layer** gets 75 plain assertions. Identity, ownership,
eligibility, both refund caps, dispatch policy, idempotency, durable counters, the
not-found wording, and grounding. No API key, because none of it touches the model.
It has passed every assertion on every run since I wrote it.

**The conversations** get 19 scenarios: six core, five concierge, eight
adversarial. Assertions read the trace, not the wording of the reply, because the
wording changes every run. Latest run 57 of 57, with 24 of 24 adversarial and no
breaches. Results in `evals/results/`.

**The suite itself** gets a negative control. Two stub agents, one refusing
everything and one claiming to have acted while touching nothing, must be rejected
by all eight adversarial scenarios. When I first ran it, five passed the
do-nothing stub. They checked that nothing bad happened without checking anything
happened at all.

### Rules hold three ways

`code_blocked` means the model tried and a check stopped it. `model_declined`
means the model was told the limit and respected it. `never_attempted` means it
never reached the boundary. Latest run: 6, 24, 9. All three are safe, and a rule
that never had to fire is the best outcome rather than a missing one.

### Five assertions I had to loosen

Each one failed a correct agent, and each change is commented in place.

| I asserted | Why it was wrong |
|---|---|
| A guardrail must have fired | A check fires only when the model misbehaves |
| `find_orders` must be called | Asking for the reference is a second correct route, and discloses less |
| `escalate_to_human` must be called | Asking for the postcode again is also correct |
| The agent must not say "your husband" | The customer said it first |
| The agent must not say "Dune" | Same. Naming the book is how you decline the request |

Two rules came out of that. A forbidden string must be one the agent could only
know from the data. And an assertion naming one correct path will eventually meet
the other one.

The obvious objection is that I loosened until everything passed. The negative
control is the answer.

---

## Known limits

**The trace holds personal data in clear.** Emails, postcodes and order references
land in it verbatim. Production needs hashed identifiers, a retention window, and
read access limited to the people handling escalations. None of that is built.

**The stores are a module-level dict.** `_REFUND_TOTALS` and
`_FAILED_VERIFICATIONS` stand in for Redis. They enforce the right invariant and do
not survive a restart.

**The cost figure rests on two conversations.** `evals/value_case.py` computes it
from tokens in the trace, four turns in total. Read it as an order of magnitude.
Cost also grows with turn count, because the whole history is resent every round.
Prompt caching is not implemented.

Identity is email plus postcode, which is weak. The caps are constants, not
settings a support manager owns. English only, UK only. No memory between
conversations.

---

## What I would change first

Move everything the prompt currently guards into code.

Two behaviours rest on instructions alone. The agent names only stocked books, and
it offers an alternative after a refusal. Both hold today. So did the refund
instruction, and I trust the refund rule because `guardrails.py` enforces it.

Then, in order. Replay the customer's real conversations rather than my nineteen
invented ones, since five of mine were wrong. Hash the identifiers in the trace.
Gate releases on the adversarial score.

All of that before any new capability. Behaviour varies between runs, so without
measurement you cannot tell a change from an improvement.
