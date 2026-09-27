import os
import time
import uuid
import json
from threading import Lock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bot import compose
from conversation_handlers import respond

START = time.time()
LOCK = Lock()
STATE = {
    "category": {}, "merchant": {}, "customer": {}, "trigger": {},
    "versions": {}, "conversations": {}
}

def now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def send_json(handler, payload, status=200):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)

def error(handler, message, status=400, **extra):
    out = {"accepted": False, "reason": message}
    out.update(extra)
    send_json(handler, out, status)

def _merchant_for(trigger):
    mid = trigger.get("merchant_id") or (trigger.get("payload") or {}).get("merchant_id")
    return STATE["merchant"].get(mid, {}) if mid else {}

def _customer_for(trigger):
    cid = trigger.get("customer_id") or (trigger.get("payload") or {}).get("customer_id")
    return STATE["customer"].get(cid) if cid else None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            send_json(self, {
                "name": "Vera Merchant AI Assistant",
                "status": "ok",
                "service": "magicpin AI Challenge",
                "endpoints": ["/v1/context","/v1/tick","/v1/reply","/v1/healthz","/v1/metadata"]
            })
        elif self.path == "/v1/healthz":
            send_json(self, {
                "status": "ok",
                "uptime_seconds": round(time.time() - START, 2),
                "contexts_loaded": {k: len(STATE[k]) for k in ("category","merchant","customer","trigger")}
            })
        elif self.path == "/v1/metadata":
            send_json(self, {
                "team_name": os.getenv("TEAM_NAME", "Arushi"),
                "team_members": [os.getenv("TEAM_MEMBER", "Arushi")],
                "model": "deterministic-context-composer",
                "approach": "trigger-routed context-grounded merchant/customer assistant",
                "contact_email": os.getenv("CONTACT_EMAIL", ""),
                "version": "1.0.0",
                "submitted_at": now_iso()
            })
        else:
            error(self, "not_found", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return error(self, "invalid_json", 400)

        if self.path == "/v1/context":
            return self.context(data)
        if self.path == "/v1/tick":
            return self.tick(data)
        if self.path == "/v1/reply":
            return self.reply(data)
        return error(self, "not_found", 404)

    def context(self, data):
        scope = data.get("scope")
        context_id = data.get("context_id")
        version = data.get("version", 1)
        payload = data.get("payload")

        if scope not in ("category","merchant","customer","trigger"):
            return error(self, "invalid_scope", details="scope must be category, merchant, customer, or trigger")
        if not context_id or payload is None:
            return error(self, "malformed_context", details="context_id and payload are required")

        key = (scope, context_id)
        with LOCK:
            current = STATE["versions"].get(key, -1)
            if version < current:
                return error(self, "stale_version", 409, current_version=current)
            if version == current:
                return send_json(self, {"accepted": True, "ack_id": f"ack_{uuid.uuid4().hex[:12]}", "stored_at": now_iso()})
            STATE[scope][context_id] = payload
            STATE["versions"][key] = version

        send_json(self, {"accepted": True, "ack_id": f"ack_{uuid.uuid4().hex[:12]}", "stored_at": now_iso()})

    def tick(self, data):
        actions, used = [], set()
        for tid in data.get("available_triggers", []):
            trigger = STATE["trigger"].get(tid)
            if not trigger:
                continue
            suppression = trigger.get("suppression_key")
            if suppression in used:
                continue

            merchant = _merchant_for(trigger)
            mid = trigger.get("merchant_id") or (trigger.get("payload") or {}).get("merchant_id")
            if not merchant or not mid:
                continue

            category_slug = merchant.get("category_slug") or (trigger.get("payload") or {}).get("category")
            category = STATE["category"].get(category_slug, {"slug": category_slug or "general", "offer_catalog": []})
            customer = _customer_for(trigger)
            result = compose(category, merchant, trigger, customer)

            conv = f"conv_{uuid.uuid4().hex[:12]}"
            cid = trigger.get("customer_id") or (trigger.get("payload") or {}).get("customer_id")
            STATE["conversations"][conv] = {
                "merchant_id": mid, "customer_id": cid,
                "trigger_id": tid, "history": [{"role":"bot","body":result["body"]}]
            }

            actions.append({
                "conversation_id": conv, "merchant_id": mid, "customer_id": cid,
                "send_as": result["send_as"], "trigger_id": tid,
                "template_name": f"vera_{trigger.get('kind','context')}_v1",
                "template_params": [], "body": result["body"], "cta": result["cta"],
                "suppression_key": result["suppression_key"], "rationale": result["rationale"]
            })
            used.add(suppression)

        send_json(self, {"actions": actions})

    def reply(self, data):
        conv_id, message = data.get("conversation_id"), data.get("message", "")
        if not conv_id or not message:
            return error(self, "malformed_reply", details="conversation_id and message are required")

        conv = STATE["conversations"].get(conv_id)
        if not conv:
            conv = {"history": [], "merchant_id": data.get("merchant_id"), "customer_id": data.get("customer_id")}
            STATE["conversations"][conv_id] = conv

        conv["history"].append({"role": data.get("from_role", "merchant"), "body": message})
        result = respond(conv, message)
        if result["action"] == "send":
            conv["history"].append({"role":"bot","body":result["body"]})
        send_json(self, result)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
