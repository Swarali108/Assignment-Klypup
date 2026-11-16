"""The control tower chat agent (api/CHAT_CONTRACT.md).

Flow for one message: router (code rules first, then the fast model) -> clarify when the question is ambiguous
-> planner (strong model, multi-step questions only) -> tools (code over api/views and api/store) -> verifier (code:
every digit in the prose must be in the tool results) -> writer (fast model for simple answers, strong model for
multi-step ones, a code template for exact lookups). Anything that spends money first returns an estimate and a
signed confirm token; nothing that spends runs without one.
"""
