#!/usr/bin/env python3
"""
Interactive chat with the Bookly agent.

    python cli.py              normal chat
    python cli.py --trace      show the tool calls and guardrail decisions inline

The --trace flag exists because this is a demo for a technical audience. In a
real deployment the same information goes to the observability pipeline instead
of the terminal, but it is the same data.
"""

import argparse
import json
import os
import sys

from bookly.agent import BooklyAgent

DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"

BANNER = f"""{BOLD}Bookly support{RESET}
{DIM}Type your message, or 'quit' to exit, or 'summary' for the conversation trace rollup.{RESET}

{DIM}Test account: priya.raman@example.com / SW1A 1AA
Orders: ORD-84201 (delivered, returnable) - ORD-84315 (in transit) - ORD-79930 (delivered 104 days ago)
Second account: tom.whitfield@example.com / M1 4BT  -  ORD-84420 (GBP 342, above auto-refund cap){RESET}
"""


def print_trace(turn):
    for e in turn.tool_events:
        colour = {"ok": GREEN, "refused": YELLOW, "error": RED}[e.outcome]
        args = json.dumps(e.arguments) if e.arguments else "{}"
        print(f"  {DIM}->{RESET} {colour}{e.tool_name}{RESET} {DIM}{args}{RESET}")
        if e.guardrail:
            mark = "PASS" if e.guardrail["permitted"] else "BLOCK"
            gcolour = GREEN if e.guardrail["permitted"] else YELLOW
            print(f"     {gcolour}[{mark}]{RESET} {DIM}{e.guardrail['rule']}: {e.guardrail['reason']}{RESET}")
        if e.cited_passages:
            print(f"     {DIM}cited: {', '.join(e.cited_passages)}{RESET}")
    print(f"  {DIM}resolution: {turn.resolution} | model round trips: {turn.model_stops}{RESET}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", action="store_true", help="Show tool calls and guardrail decisions.")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first.", file=sys.stderr)
        return 1

    agent = BooklyAgent()
    print(BANNER)

    while True:
        try:
            message = input(f"{CYAN}you{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not message:
            continue
        if message.lower() in {"quit", "exit"}:
            break
        if message.lower() == "summary":
            print(json.dumps(agent.tracer.summary(), indent=2))
            continue

        reply = agent.send(message)

        if args.trace:
            print()
            print_trace(agent.tracer.turns[-1])

        print(f"\n{BOLD}bookly{RESET} {reply}\n")

    print(f"\n{DIM}{json.dumps(agent.tracer.summary())}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
