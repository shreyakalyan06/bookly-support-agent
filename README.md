# Bookly support agent

A support agent for a fictional online bookshop. It runs on Python and calls the Anthropic API directly. I wrote the loop by hand because the brief asked to avoid frameworks. In production a platform owns the loop and an engineer will own the procedures, the tools and the checks.

There are 2 support jobs end to end: where is my order, and I want to send this back,
refund included. It also answers policy questions and suggests a book after
declining a return.

## Run it

Python 3.10 or newer.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python cli.py --trace                        # chat, with the tool calls shown
python evals/test_control_layer.py           # 56 checks, no API key needed
python evals/run_scenarios.py --repeats 3    # 14 conversations, needs a key
```
# Test customers and their orders.

| Customer | Credentials | Orders |
|---|---|---|
| Priya Raman | `priya.raman@example.com` / `SW1A 1AA` | `ORD-84201` returnable · `ORD-84315` in transit · `ORD-79930` delivered 104 days ago |
| Tom Whitfield | `tom.whitfield@example.com` / `M1 4BT` | `ORD-84420` £342, over the cap · `ORD-84501` return already running |

Priya holds two open orders, so "where is my order" has no single answer and the
agent has to ask.

## The design

Most of what a support agent does belongs in plain English. The tone, the
sequencing, when to ask instead of act, how to recover from a no. These change
weekly and a support manager should change them without waiting for a deploy.

The line is drawn by reversibility as opposed to how much you trust the model. Anything
irreversible gets a check in code as well because a limit written in text is a
request and a customer will push on it.

The model picks what to attempt. `guardrails.py` decides whether it is allowed.
That file imports nothing to do with the model and never reads the conversation,
so no wording a customer chooses changes its answer.

`agent.py` checks `guardrails.TOOL_POLICY` before calling any handler. Iff a tool is missing from that table, agent.py refuses it, so a new tool fails closed. A test walks both tables and fails on any mismatch

Actions are sorted by one question: if this goes wrong, does it reverse?

| Tier | Actions | Gate | Cost of an error |
|---|---|---|---|
| 0 | policy lookup, recommendations | none | a correction |
| 1 | order list, order detail | identity verified | another customer's data |
| 2 | returns and refunds | four checks, £100 cap | money, and it does not come back |

Closing the refund path is what lets tier 0 stay open. Recommendations get no check on purpose.

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

**The refund limits get a check in code as well as a line in the prompt.** Costs
flexibility: a fair exception gets blocked and needs a person. It is worth it because a
refund does not come back, and 56 offline checks prove the limits hold without
spending anything on the API. The prompt still owns how the agent explains the
refusal. 

**The agent quotes policy only after retrieving the passage, and cites the passage.**
Deflection drops and resolved-correctly rises. Worth it because without a cutoff there is always a least bad match, and a gift card passage will confidently answer a question about loyalty points.

**An unclear request gets a question and not a guess.** That just costs one extra message.
it is worth it because guessing right usually means cancelling the wrong order sometimes.

Two smaller ones. Chat rather than voice, because in four hours voice spends the
budget on speech handling instead of on the permission design. The tool layer, the
permission layer and the trace do not care about the channel. Voice changes the
transport, the latency budget, and reading an irreversible action back before doing
it. It does not change any of the checks.

Recommendations use weighted arithmetic on theme and mood instead than a second model
call, so they are free, repeatable, and every suggestion carries a reason.

## Testing

The permission layer gets 56 plain assertions and no API key, because none of it
touches the model. The conversations get 14 scenarios, six of them attacks.
Assertions read the trace rather than the wording of the reply, because the
wording changes every run and the trace does not.

`test_eval_suite.py` is a negative control. Two stub agents, one refusing
everything and one claiming to have acted while touching nothing, must be rejected
by every attack scenario. When I first ran it, five scenarios passed the stub that did nothing.
they checked that nothing bad happened without checking anything happened at all.

No assertion covers the recovery offer as nothing enforces it. Across
runs it has appeared anywhere between one time in three and every time. That
spread argues well for moving it into code rather than a reason to loosen a
test.

Amy own assertions failed a correct agent eight times and had to change. Requiring a
guardrail to have *fired* meant the test only passed if the model misbehaved.
Requiring `find_orders`, then `get_order`, then `escalate_to_human` each ruled out
a second correct path. Refusing without a lookup, or asking for the reference
instead of listing everything, discloses less and is better service.
Forbidding "your husband", then "Dune", then any bold title the customer had named,
all forbade the agent from repeating the customer back. This resulted in 2 new rules. A forbidden string must be one the agent could only
know from the data. And an assertion naming one correct path will eventually meet
the other one, which happened to me eight times.

Results in `evals/results/`.

The full suite is 42 real conversations and takes about ten minutes. Almost all of
that is waiting on the model, roughly fourteen seconds a conversation. While
iterating, use `--repeats 1` for three minutes, or `--only adv` for one group, and
save the three-repeat run for before you commit.

It runs one at a time on purpose. Parallel runs needed each worker to have its own
copy of the order data, and that copy was what let the same refund succeed once per
worker. Faster and unsound is not a trade worth making in the file whose job is
proving the refund path holds.

**On the score.** Thirteen scenarios at three repeats. A clean sweep means no
failures observed, which is not the same as no failures possible, and thirteen
different scenarios are not thirteen trials of one thing so there is no single rate
to quote. The offline checks are a different kind of claim: those hold by
construction rather than by sampling. I had a confidence interval here and got the
arithmetic wrong, so it is gone.

## Known limits

Identity is email plus postcode, which is weak. In a real deployment a signed
session token from the host page gets verified server side and
`verified_customer_id` is populated before the first turn, so `verify_customer`
disappears entirely.

The £100 cap is a module constant. It should be authored by the business, resolved
in code, and versioned, so raising it to £150 is a config change rather than a pull
request.

The trace records messages verbatim, so emails and postcodes land in it in clear.
Production needs hashed identifiers and a retention window.

The refund cap is per decision, not per customer. Four separate £75 refunds each
pass it. A rolling total keyed by customer closes that, and needs a store that
outlives a conversation.

**Nothing survives the process.** Sessions are in memory, orders are a module dict,
and every conversation appends to one trace file. No horizontal scaling story beyond
sticky sessions.

**`recommend_books` used to take `use_purchase_history`, and I cut it.** With that
flag the same tool read a customer's orders, so its risk followed the arguments
rather than the name, and the dispatcher only sees the name. Splitting the tool or
making dispatch argument-aware both work. Cutting the flag was the cheaper honest
option and it kept the tier table true. "Same function, two risk levels" was the
sharper observation and it is the thing I would put back first.

**The prompt and the caps are not config.** The prompt is a string literal in
`agent.py` and the cap is a module constant, so only an engineer can change either.
The business should author both and the code should resolve them. That is the change
I would make first and the reason it is not done is scope, not disagreement.

**No wall-clock deadline and no history trimming.** Worst case is eight rounds at a
thirty second timeout, and the whole history is resent every round, so a long
conversation gets slower and dearer as it goes.

**Two races I know about and have not closed.** Duplicate returns are caught by a
list on the order, so two workers reading it at the same time could both get
through. And when a model call fails mid-turn the message history rolls back, but a
refund committed in an earlier round does not, so the conversation loses its record
of something that happened. Both need a store with a transaction, which is the same
change as the point above.

**`escalate_to_human` records a handoff, it does not enforce one.** The agent keeps
taking turns afterwards, and the handoff carries a reason and a summary rather than
a real artefact. The trace already holds the tool trail, the passages cited and the
verified status, so the useful version hands all of that to the person picking the
conversation up. That is what I would build, and it is the thing a support lead asks
about first.

**The worst case is eight rounds at a thirty second timeout**, so four minutes on
one message. A wall clock deadline per message is what production needs.

**The model string is an alias, not a dated snapshot**, so the committed numbers are
reproducible only until the alias moves. Temperature is not set either, because the
model rejects it, so two runs of the same scenario will not match exactly. That is
the whole reason the assertions read the trace rather than the wording.

Date fixtures are computed at import while the checks call `date.today()`, so a
process running for a month drifts. English only, UK only. No memory between
conversations.

## What I would change first

Pull the prompt and the two limits into a config file. Right now the prompt is a
string literal inside `agent.py` and the cap is a module constant, so nobody but an
engineer can change either. That is backwards: the business should author both and
the code should resolve them.

Then give a check to the two behaviours that only have a line of text. The agent
names only stocked books, and it offers an alternative after a refusal. Both hold
today, and so did the refund instruction before I gave it a check.

Then replay real conversations rather than my fourteen invented ones, since eight
of my assertions were wrong. Then a durable store, which gives cross-conversation
verification, a rolling per-customer refund total, and a trace that survives a
restart, all from the same change. Then the per-customer refund total. Then gate releases on the
attack score.

All of that before new capability. Behaviour varies between runs, so without
measurement you cannot tell a change from an improvement.
