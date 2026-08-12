# Bookly support agent

A customer support agent for a fictional online bookstore, built for the Decagon
Solutions Engineering take-home.

## The thesis

An agent's value is in **completed actions**, not good answers. But the moment an
agent can act, "please behave" stops being a control.

So this agent is built on one rule: **the model decides what to attempt, and
deterministic code decides what is permitted.** Those are different jobs and they
live in different files. The system's limits do not depend on how persuasive the
customer is, and they do not change when the model does.

The obvious objection is that this produces something too restrictive to be
useful. That objection assumes every action deserves the same suspicion, and the
second half of the thesis is that it does not. **Authority should be tiered by
how recoverable an action is.**

| Tier | Actions | Gate | Cost of getting it wrong |
|---|---|---|---|
| 0 informational | policy lookup, recommendations, book clubs | none | a correction |
| 1 account read | order list, order detail | identity verified | someone else's data leaked |
| 2 irreversible | returns and refunds | full authorisation chain | money and trust |

A bad refund cannot be undone. A bad book recommendation costs nothing. So the
agent is tightly constrained on one and deliberately generous on the other.

That is why a control layer makes an agent **more** capable rather than less: once
the irreversible actions are structurally safe, you can stop being defensive about
everything else. Bookly's agent recommends books, remembers what you have already
bought, and invites you to a reading group discussing the thing you just finished —
none of which would be a comfortable thing to ship if the return window lived in
a prompt.

### The scenario this is all built around

A customer wants to return a book delivered 104 days ago.

The guardrail holds — `check_returnable` refuses, and no amount of persuasion
moves it. But the customer still has a book they did not enjoy, and a bare refusal
loses them. So the agent refuses, then finds them something they might prefer and
a group discussing the book they bounced off.

On a containment metric those two conversations look identical. The difference
between them is the entire commercial argument for this category, which is why
the trace records `recovery_offered` as its own field and `recovery_rate_on_refusals`
is a conversation-level metric.

## Architecture

```
customer message
       |
   agent.py          orchestration loop, hand-rolled tool calling
       |             (no framework -- the loop is ~15 lines of real logic)
       |
   tools.py          tool schemas + handlers. Every account-touching handler
       |             calls the control layer BEFORE doing any work.
       |
  guardrails.py      the control layer. Knows nothing about the model, the
       |             conversation, or how the request was phrased.
       |
  data.py            orders and customers   |  catalogue.py  books and reading groups
       |             policy.py  retrieval + citations
       |
   trace.py          structured record of every decision, as JSON lines
```

### Why the guardrails are not in the prompt

The system prompt does tell the agent to verify identity and respect the return
window. That instruction is there for **conversational quality** — so the agent
asks for a postcode gracefully instead of trying, failing, and then asking.

But the instruction is not the control. `guardrails.py` is. If the prompt were
deleted entirely, the agent would be clumsy and it would still be unable to read
an unverified customer's order, refund outside the window, or approve more than
the value cap.

That property is testable, and `evals/scenarios.py` tests it — the adversarial
scenarios are direct attempts to talk the agent past its constraints.

### The four rules that live in code

| Rule | Where | Why not the prompt |
|---|---|---|
| Identity verified before any account access | `check_identity` | The most damaging failure is leaking one customer's data to another |
| Verified customer sees only their own orders | `check_ownership` | Same, and the refusal deliberately does not confirm the order exists |
| Returns only on delivered orders inside 30 days | `check_returnable` | Date arithmetic is not what a language model is good at |
| Autonomous refunds capped at GBP 100 | `check_refund_value` | Above the cap the agent does all the work; a human authorises the money |

And one deliberate absence: there is **no** `check_recommendation`. Being able to
say why an action has no guardrail is as much a part of the design as the
guardrails. The only constraint on recommendations is grounding, not authority —
suggestions must resolve to a real, in-stock catalogue entry, because a
recommendation for a book Bookly cannot sell creates a support ticket instead of
closing one. That lives in the tool, since it is about truthfulness rather than
permission.

Note also that `recommend_books` with `use_purchase_history` inherits the Tier 1
identity gate. The tier follows **the data an action touches**, not the tool's
name.

## Running it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python cli.py                 # chat
python cli.py --trace         # chat, with tool calls and guardrail decisions shown
```

Test accounts:

| Customer | Credentials | Orders |
|---|---|---|
| Priya Raman | `priya.raman@example.com` / `SW1A 1AA` | `ORD-84201` delivered 6 days ago, returnable · `ORD-84315` in transit · `ORD-79930` delivered 104 days ago |
| Tom Whitfield | `tom.whitfield@example.com` / `M1 4BT` | `ORD-84420` GBP 342, above the auto-refund cap · `ORD-84501` return already in progress |

## Evaluation

Two suites, deliberately separate.

```bash
python evals/test_control_layer.py          # no API key needed, no network
python evals/run_scenarios.py --repeats 3   # behavioural, needs an API key
```

**`test_control_layer.py`** tests the deterministic half — 27 assertions on
identity, ownership, eligibility, value ceilings, duplicate guards, and policy
retrieval thresholds. It runs with no API key because none of it touches the
model. It should be 100%, every time, or something is broken.

**`run_scenarios.py`** tests the conversational half. Eighteen scenarios: six core,
five concierge, seven adversarial. Assertions are made against the **trace**, not against the
wording of the reply — "did it verify before reading the order" is stable, "did
it say the right sentence" is not. Run with `--repeats` to get a pass rate rather
than a single sample, because a non-deterministic system that passed once has not
been shown to pass.

Being able to draw that line — this half gets unit tests, that half gets
statistical evaluation — is the practical payoff of putting the constraints in
code.

## Deliberate scope choices

**Chat, not voice.** Voice would have consumed the budget on speech-to-text,
text-to-speech and latency management without demonstrating anything about the
control architecture. Chat let me spend it on the part I think is actually hard.

**Keyword retrieval, not embeddings.** For nine passages, embeddings add an API
dependency and a similarity threshold that is harder to reason about, in exchange
for better paraphrase handling. At a real help centre's scale I would use hybrid
retrieval — BM25 plus embeddings with rank fusion. What would *not* change is the
citation contract and the "return nothing below threshold" rule. Those are
architectural; the retriever is an implementation detail.

**Two support use cases, properly.** Order status and returns, taken end to end,
including their refusal paths. Not five use cases handled shallowly.

**Recommendations computed, not generated.** Similarity is weighted overlap on
theme, mood, genre and pace — arithmetic, not a second model call. It is instant,
free, identical every time, and I can explain why any given book was suggested.
None of those are true of asking a model to free-associate, and "why did you
recommend that" is a question a merchandising team will ask on day one.

**One guard against the concierge behaviour becoming a tic.** The
`concierge-angry-no-upsell` scenario asserts that a furious customer chasing a
late delivery gets their problem solved and nothing else. A recommendation there
would be tone-deaf, and a feature that cannot tell the difference is a liability.

## What I would do first in production

Build the evaluation harness out before adding a single new capability.

The scenario suite here is hand-written and small. In production I would:

1. Replay the customer's own historical conversations against the agent and diff
   the outcome against what the human agent actually did. This is far more
   convincing in a sales cycle than a curated demo, because it uses their data.
2. Generate adversarial conversations rather than writing them by hand.
3. Wire the trace into a warehouse table, so containment, refusal reasons and
   citation coverage are dashboard metrics rather than things someone greps for.
4. Add a regression gate: no prompt or AOP change ships if the adversarial pass
   rate drops.

The reason this comes before new features: with a non-deterministic system you
cannot otherwise tell whether a change improved things or merely changed them.

## Known limits

- Identity verification on email plus postcode is weak by design — a real
  deployment would use existing account auth or step-up verification. The
  structural point is that *something* gates it, in code.
- No cross-session memory. Each conversation starts cold.
- The value cap is a constant. In production it belongs in a policy service so
  CX operations can change it without a deploy — but it still resolves outside
  the model.
- Retrieval is single-language and single-market.
