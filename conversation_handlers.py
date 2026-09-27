"""Optional lightweight multi-turn handler for replay/tiebreaker scenarios."""

import re

AUTO_REPLY_MARKERS = (
    "thank you for contacting us",
    "our team will respond shortly",
    "thank you for contacting",
    "automated assistant",
)

STOP_MARKERS = (
    "stop messaging",
    "don't message",
    "do not message",
    "not interested",
    "no thanks",
    "unsubscribe",
)

ACTION_MARKERS = (
    "yes",
    "go ahead",
    "let's do it",
    "lets do it",
    "proceed",
    "do it",
    "send it",
    "send me",
    "update it",
    "please do",
)

def respond(state, merchant_message):
    msg = (merchant_message or "").strip().lower()
    history = getattr(state, "history", state.get("history", []) if isinstance(state, dict) else []) or []

    if any(x in msg for x in STOP_MARKERS):
        return {"action": "end", "rationale": "Merchant explicitly declined or requested no further messaging."}

    if any(x in msg for x in AUTO_REPLY_MARKERS):
        repeats = sum(1 for h in history if str(h.get("message", h.get("body", ""))).strip().lower() == msg)
        if repeats >= 1:
            return {"action": "end", "rationale": "Repeated canned reply detected; stopping rather than burning turns."}
        return {"action": "wait", "wait_seconds": 900, "rationale": "Likely automated reply; waiting for a human response."}

    if any(re.search(r"\b" + re.escape(x) + r"\b", msg) for x in ACTION_MARKERS):
        return {
            "action": "send",
            "body": "Done — moving to the next step now. I’ll keep the details grounded in the information you’ve already provided.",
            "cta": "open_ended",
            "rationale": "Explicit action intent detected; switched from qualification to execution."
        }

    return {
        "action": "send",
        "body": "Got it. I’ll keep this focused on the specific point you raised rather than restarting the qualification.",
        "cta": "open_ended",
        "rationale": "Acknowledged the latest merchant turn without re-asking settled questions."
    }
