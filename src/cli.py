from __future__ import annotations

import sys

from src.engine import RecommendationEngine
from src.session import SessionStore

WELCOME = (
    "Fashion shopping assistant (catalogue-only recommendations).\n"
    "Tell me the occasion, budget, size, and style. Type 'quit' to exit.\n"
)


def main() -> None:
    engine = RecommendationEngine()
    sessions = SessionStore()
    chat_id = "cli"
    print(WELCOME)
    if not engine.grok.available:
        print("(GROQ_API_KEY not set — using template replies.)\n")

    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not line:
            continue
        if line.lower() in {"quit", "exit", "q"}:
            print("Bye.")
            break
        slots = sessions.get(chat_id)
        reply = engine.handle_message(chat_id, line, slots)
        sessions.update(chat_id, slots)
        print(f"\nAssistant: {reply}\n")


if __name__ == "__main__":
    main()
    sys.exit(0)
