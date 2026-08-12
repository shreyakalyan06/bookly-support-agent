# Bookly support agent

A customer support agent for a fictional online bookshop, built for the Decagon
Solutions Engineering take-home.

## The thesis

Answering questions is cheap. Finishing the job is what customers came for, and
it is where the risk starts. Once an agent can move money, a prompt instruction
stops counting as a control.

So this agent runs on one rule. **The AI proposes. Code approves.** Two jobs, so
two places. Nobody can argue the agent past its limits, because it never held the
power to break them.

The usual objection is that this produces something too locked down to sell. That
assumes every action carries the same risk. Sort them by whether a mistake can be
undone.

| Tier | Actions | Gate | Cost of getting it wrong |
|---|---|---|---|
| 0 informational | policy lookup, recommendations, book clubs | none | a correction |
| 1 account read | order list, order detail | identity verified | someone else's data leaked |
| 2 irreversible | returns and refunds | full authorisation chain | money and trust |

A bad refund cannot be undone. A bad book suggestion costs nothing. Lock down the
money and you can afford to be generous with everything else.

That is why a control layer makes the agent more capable rather than less. Once
the irreversible actions are safe by construction, you can stop being defensive
about the rest. Bookly's agent recommends books, remembers what you already
bought, and invites you to a reading group. None of that would be comfortable to
ship with the return window living in a prompt.

### The scenario it is built around

A customer wants to return a book delivered 104 days ago.

`check_returnable` refuses, and no amount of persuasion moves it. But the
customer still owns a book they did not enjoy, and a bare refusal loses them. So
the agent refuses, then finds them something they might prefer and a group
discussing the book they bounced off.

Both conversations look identical on a containment metric. The gap between them is
the commercial case for this category. The trace records `recovery_offered` as its
own field and reports `recovery_rate_on_refusals` per conversation.

## Architecture

```
customer message
       |
   agent.py          orchestration loop, hand-rolled tool calling
       |             no framework, so the loop stays readable
       |
   tools.py          tool schemas and handlers. Account-touching handlers
       |             call the control layer before doing any work.
       |
  guardrails.py      the control layer. Knows nothing about the model,
       |             the conversation, or how a request was phrased.
       |
  data.py            orders and customers    catalogue.py  books and clubs
       |             policy.py  retrieval and citations
       |
   trace.py          every decision recorded as JSON lines
```

### Why the guardrails are not in the prompt

The system prompt does tell the agent to verify identity and respect the return
window. That is there for conversational quality, so it asks for a postcode
gracefully instead of trying, failing, then asking.

The instruction is not the control. `guardrails.py` is. Delete the prompt and the
agent turns clumsy while remaining unable to read an unverified customer's order,
refund outside the window, or approve more than the value cap.

That property is testable. The adversarial scenarios in `evals/scenarios.py` are
direct attempts to talk the agent past its constraints.

### The four rules that live in code

| Rule | Where | Why not the prompt |
|---|---|---|
| Identity verified before any account access | `check_identity` | Leaking one customer's data to another is the worst outcome available |
| Verified customer sees only their own orders | `check_ownership` | Same, and the refusal deliberately does not confirm the order exists |
| Returns only on delivered orders inside 30 days | `check_returnable` | Date arithmetic is not what a language model is good at |
| Autonomous refunds capped at £100 | `check_refund_value` | Above the cap the agent does the work and a human authorises the money |

There is deliberately no `check_recommendation`. Being able to say why an action
has no guardrail is part of the design. The only constraint on recommendations is
grounding, not authority: suggestions must resolve to a real, in-stock catalogue
entry, because recommending a book Bookly cannot sell creates a ticket rather than
closing one. That lives in the tool, since it concerns truthfulness rather than
permission.

Note that `recommend_books` with `use_purchase_history` inherits the Tier 1
identity gate. The tier follows the data an action touches, not the tool's name.

## Running it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python cli.py                 # chat
python cli.py --trace         # chat, showing tool calls and guardrail decisions
```

Test accounts:

| Customer | Credentials | Orders |
|---|---|---|
| Priya Raman | `priya.raman@example.com` / `SW1A 1AA` | `ORD-84201` delivered 6 days ago, returnable · `ORD-84315` in transit · `ORD-79930` delivered 104 days ago |
| Tom Whitfield | `tom.whitfield@example.com` / `M1 4BT` | `ORD-84420` £342, above the auto-refund cap · `ORD-84501` return already in progress |

## Evaluation

Two suites, deliberately separate.

```bash
python evals/test_control_layer.py           # no API key, no network
python evals/run_scenarios.py --repeats 3    # behavioural, needs an API key
```

**`test_control_layer.py`** covers the deterministic half. 48 assertions on
identity, ownership, eligibility, value ceilings, duplicate guards, tier
assignment and grounding. It needs no API key because none of it touches the
model. It should be 100% every time.

**`run_scenarios.py`** covers the conversational half. Eighteen scenarios: six
core, five concierge, seven adversarial. Assertions run against the **trace**, not
the wording of the reply. "Did it verify before reading the order" is stable.
"Did it say the right sentence" is not. Use `--repeats` for a pass rate, since a
non-deterministic system that passed once has not been shown to pass.

Drawing that line is the practical payoff of putting constraints in code. One
half gets unit tests. The other needs statistical measurement.

### Results

Latest full run, 18 scenarios at 3 repeats, in `evals/results/`.

- 48/48 control-layer assertions, every run
- 21/21 adversarial runs held, zero breaches
- `concierge-refusal-recovery` at 67%

That last figure is the interesting one. Recovery after a refusal is the only
behaviour in the system with no code behind it, and it is the only one that
varies. Everything moved into code became completely reliable.

### What the evaluator taught me

The agent never failed a run. Five times a test failed it, and each time the test
was wrong:

1. `clarifying` classified by a trailing question mark, which misfiled any reply
   that asked something then closed politely.
2. Fixed to "question mark anywhere", which then misfiled every courtesy closer.
   The fix introduced a new failure.
3. Asserting that a guardrail **fired**, which requires the model to misbehave
   first. Three scenarios failed while behaving perfectly, because the agent read
   the constraint from the tool payload and declined without attempting anything.
4. `recommended` overwriting the primary outcome inside a turn, so a correct
   refusal followed by a helpful suggestion was reclassified.
5. `expect_resolution_in` reading the final turn rather than the primary outcome.
   I patched this by hand three times before fixing the design.

The control-layer suite was right first time and never changed. Anything moved
into code becomes verifiable in a way that leaves no room to fool yourself.

## Deliberate scope choices

**Chat, not voice.** Voice would have spent the budget on speech handling and
latency without demonstrating anything about the control architecture.

**Keyword retrieval, not embeddings.** For nine passages, embeddings add an API
dependency and a similarity threshold that is harder to reason about. At a real
help centre's scale I would use hybrid retrieval, BM25 plus embeddings with rank
fusion. The citation contract and the "return nothing below threshold" rule would
not change. Those are architectural. The retriever is an implementation detail.

**Two support use cases, properly.** Order status and returns end to end,
including their refusal paths.

**Recommendations computed, not generated.** Similarity is weighted overlap on
theme, mood, genre and pace. Arithmetic, not a second model call. Instant, free,
identical every time, and every suggestion carries a reason. A merchandising team
asks "why did it recommend that" on day one.

**One guard against the concierge behaviour becoming a tic.** The
`concierge-angry-no-upsell` scenario asserts that a furious customer chasing a
late delivery gets their problem solved and nothing else.

## What I would do first in production

1. Make recovery a rule rather than a request. If the commercial case depends on
   it, 67% is not good enough, and the fix is structural: require an alternative
   before a refusal turn can close.
2. Validate outgoing titles against the catalogue before the message leaves. The
   agent is told to name only books we stock, and that instruction holds today.
   So did the refund instruction, and I trust the refund rule because code
   enforces it.
3. Replay the customer's own conversation history and compare the agent's
   decisions against what their team actually did. More convincing than any demo,
   because it uses their data.
4. Gate releases on the adversarial pass rate.

Evaluation comes before new capability. With a system that varies run to run you
cannot otherwise tell an improvement from a change.

## Known limits

- Identity verification on email plus postcode is weak by design. A real
  deployment would use existing account auth or step-up verification. The
  structural point is that something gates it, in code.
- No cross-session memory. Each conversation starts cold.
- The value cap is a constant. In production it belongs in a policy service so CX
  operations can change it without a deploy, resolved outside the model.
- Retrieval is single-language and single-market.
