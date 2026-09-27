"""
magicpin AI Challenge — Vera-style merchant assistant
Dependency-free, deterministic composer.

The composer deliberately uses only facts present in the supplied contexts.
It routes trigger kinds to category-aware message shapes, then falls back to a
specific performance/offer/context nudge for unseen trigger kinds.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional


def _identity(merchant):
    return merchant.get("identity", {}) or {}


def _owner(merchant):
    ident = _identity(merchant)
    name = ident.get("owner_first_name") or ident.get("name") or "there"
    return name


def _name_for_customer(customer):
    return ((customer or {}).get("identity", {}) or {}).get("name") or "there"


def _category(category, merchant):
    return category.get("slug") or merchant.get("category_slug") or ""


def _active_offers(merchant):
    return [
        o.get("title")
        for o in merchant.get("offers", []) or []
        if o.get("status") == "active" and o.get("title")
    ]


def _find_offer(merchant, needle):
    n = needle.lower()
    for o in merchant.get("offers", []) or []:
        if o.get("status") == "active" and n in o.get("title", "").lower():
            return o.get("title")
    return None


def _first_offer(category, kind=None):
    offers = category.get("offer_catalog", []) or []
    if kind:
        for o in offers:
            if o.get("type") == kind:
                return o.get("title")
    return offers[0].get("title") if offers else None


def _pct(x):
    try:
        return f"{abs(float(x)) * 100:.0f}%"
    except Exception:
        return str(x)


def _pct_signed(x):
    try:
        return f"{float(x) * 100:+.0f}%"
    except Exception:
        return str(x)


def _last_topic(merchant):
    hist = merchant.get("conversation_history", []) or []
    return hist[-1].get("body", "") if hist else ""


def _rationale(kind, fact):
    return f"Uses the {kind} trigger as the reason for contact and anchors the message on {fact}."


def _merchant_action(category, merchant, trigger):
    """Merchant-facing deterministic routing."""
    cat = _category(category, merchant)
    kind = trigger.get("kind", "")
    p = trigger.get("payload", {}) or {}
    ident = _identity(merchant)
    owner = _owner(merchant)
    biz = ident.get("name", "your business")
    locality = ident.get("locality", "")
    perf = merchant.get("performance", {}) or {}
    active = _active_offers(merchant)

    # Planning: continue an already-explicit intent; do not re-qualify.
    if kind == "active_planning_intent":
        topic = p.get("intent_topic", "the idea")
        last = p.get("merchant_last_message", "")
        if "corporate_bulk" in topic or "thali" in topic:
            current = _find_offer(merchant, "thali") or _first_offer(category, "service_at_price")
            body = (
                f"{owner}, picking up your corporate-bulk thali idea for {biz}. "
                f"Your current {current or 'thali offer'} gives us a concrete base. "
                f"I can turn this into a 3-tier office package with delivery terms and a WhatsApp draft. "
                f"Want me to draft that now?"
            )
        elif "kids_yoga" in topic:
            body = (
                f"{owner}, picking up the kids-yoga summer camp idea. "
                f"I can turn it into a ready-to-share plan with age band, session format, pricing structure "
                f"and a parent WhatsApp draft. Want me to draft it now?"
            )
        else:
            body = (
                f"{owner}, picking up the {topic.replace('_', ' ')} idea. "
                f"I can turn it into a ready-to-use plan and draft the customer message. Want me to draft it now?"
            )
        return body, "open_ended", _rationale(kind, f"explicit planning intent: {topic}")

    if kind == "research_digest":
        top = p.get("top_item", {}) or {}
        title = top.get("title") or "the latest category research"
        source = top.get("source")
        n = top.get("trial_n")
        segment = top.get("patient_segment")
        if n and segment:
            detail = f"{n:,}-participant work on {segment.replace('_',' ')}"
        else:
            detail = title
        source_text = f" — {source}" if source else ""
        body = f"{owner}, one useful item landed: {detail}. {title}{source_text}. Worth a 2-minute look — want me to pull the key takeaway?"
        return body, "open_ended", _rationale(kind, "the cited research item")

    if kind in {"supply_alert", "regulation_change"}:
        batches = p.get("affected_batches")
        if batches:
            batch_text = ", ".join(batches)
            fact = f"{p.get('molecule','medicine')} batches {batch_text}"
            body = (
                f"{owner}, urgent: the {p.get('molecule','affected medicine')} alert covers batches {batch_text} "
                f"from {p.get('manufacturer','the listed manufacturer')}. "
                f"I can help turn this into an affected-customer list and a replacement workflow. Want me to prepare that?"
            )
        else:
            deadline = p.get("deadline_iso", "")
            fact = f"the {p.get('category', cat)} compliance update"
            body = (
                f"{owner}, compliance update for {cat}: the new item is due by {deadline or 'the stated deadline'}. "
                f"I can turn the change into a short checklist for your team. Want me to draft it?"
            )
        return body, "open_ended", _rationale(kind, fact)

    if kind == "cde_opportunity":
        body = (
            f"{owner}, there’s a relevant training opportunity: {p.get('credits','')} credits, "
            f"{p.get('fee','fee details in the listing')}. "
            f"I can pull the item and give you the key details in one message. Want me to?"
        )
        return body, "open_ended", _rationale(kind, "the available credits and fee")

    if kind == "competitor_opened":
        comp = p.get("competitor_name", "a nearby competitor")
        dist = p.get("distance_km")
        offer = p.get("their_offer")
        detail = f"{comp} opened {dist} km away" if dist is not None else comp
        if offer:
            detail += f" with {offer}"
        body = (
            f"{owner}, heads-up: {detail}. "
            f"Your current listing is at {perf.get('ctr','?')} CTR; I can draft a response using your existing positioning "
            f"rather than copying their offer. Want me to?"
        )
        return body, "open_ended", _rationale(kind, detail)

    if kind in {"perf_dip", "perf_spike"}:
        metric = p.get("metric", "performance")
        delta = p.get("delta_pct")
        window = p.get("window", "7d")
        if delta is not None:
            change = _pct_signed(delta)
            direction = "down" if float(delta) < 0 else "up"
            body = (
                f"{owner}, your {metric} is {change} over {window}. "
                f"{'That is worth addressing now.' if float(delta) < 0 else 'That is a useful signal to build on.'} "
                f"I can suggest one concrete next step using your current listing and offers. Want me to?"
            )
            fact = f"{metric} changing {change} over {window}"
        else:
            body = (
                f"{owner}, I spotted a {kind.replace('_',' ')} on {biz}. "
                f"I can break down the signal against your current listing and suggest one next step. Want me to?"
            )
            fact = f"the {kind} signal"
        return body, "open_ended", _rationale(kind, fact)

    if kind == "milestone_reached":
        metric = p.get("metric", "milestone")
        now = p.get("value_now")
        milestone = p.get("milestone_value")
        if now is not None and milestone is not None:
            body = (
                f"{owner}, {biz} is at {now} {metric.replace('_',' ')} — only {int(milestone)-int(now)} to go for {milestone}. "
                f"I can draft a short post to help you make the milestone visible. Want me to?"
            )
            fact = f"{now} versus the {milestone} milestone"
        else:
            body = f"{owner}, you’ve got a {metric.replace('_',' ')} milestone signal. Want me to turn it into a ready-to-post update?"
            fact = "the milestone trigger"
        return body, "open_ended", _rationale(kind, fact)

    if kind == "dormant_with_vera":
        days = p.get("days_since_last_merchant_message")
        topic = p.get("last_topic")
        body = (
            f"{owner}, it’s been {days} days since we last spoke"
            + (f" about {topic.replace('_',' ')}" if topic else "")
            + f". I spotted a fresh, specific thing for {biz} and can handle the first draft for you. Want to see it?"
        )
        return body, "open_ended", _rationale(kind, f"{days} days since the last merchant message")

    if kind == "festival_upcoming":
        fest = p.get("festival", "the upcoming festival")
        days = p.get("days_until")
        active_offer = active[0] if active else _first_offer(category, "service_at_price")
        body = (
            f"{owner}, {fest} is {days} days away. "
            f"{'You already have ' + active_offer + ' active.' if active_offer else 'You have no active offer listed.'} "
            f"I can turn that into one category-appropriate {fest} post without inventing a new discount. Want me to draft it?"
        )
        return body, "open_ended", _rationale(kind, f"{fest} in {days} days")

    if kind == "category_seasonal":
        trends = p.get("trends", [])
        joined = ", ".join(str(x).replace("_", " ") for x in trends[:3])
        body = (
            f"{owner}, summer demand is shifting: {joined}. "
            f"For {biz}, I’d focus the shelf/message on the rising categories rather than the broad season. "
            f"Want me to draft the exact shelf-change checklist?"
        )
        return body, "open_ended", _rationale(kind, "the supplied seasonal demand deltas")

    if kind == "gbp_unverified":
        uplift = _pct(p.get("estimated_uplift_pct", ""))
        path = p.get("verification_path", "the available verification path")
        body = (
            f"{owner}, your Google profile is still unverified. The supplied estimate is up to {uplift} uplift, "
            f"with verification via {path.replace('_',' ')}. Want me to turn the verification path into a short checklist?"
        )
        return body, "open_ended", _rationale(kind, f"unverified status and {uplift} estimated uplift")

    if kind == "ipl_match_today":
        match = p.get("match", "today's IPL match")
        venue = p.get("venue", "")
        time = p.get("match_time_iso", "")
        weeknight = p.get("is_weeknight")
        offer = _find_offer(merchant, "Buy 1 Pizza") or (active[0] if active else None)
        if weeknight is False:
            advice = "Because this is a non-weeknight match, I’d avoid assuming a dine-in lift."
        else:
            advice = "This is the kind of match-night window where a targeted offer can make sense."
        body = (
            f"{owner}, {match} is at {venue} at {time}. {advice} "
            f"{'You already have ' + offer + ' active.' if offer else 'I can work from your current offer set.'} "
            f"Want me to draft the match-day message?"
        )
        return body, "open_ended", _rationale(kind, f"{match} at {venue}")

    if kind == "curious_ask_due":
        ask = p.get("ask_template", "what is moving this week")
        body = (
            f"Hi {owner} — quick operator check: {ask.replace('_',' ')}? "
            f"Give me the one service/product you’re hearing about most and I’ll turn it into a usable post or reply draft."
        )
        return body, "open_ended", _rationale(kind, "the scheduled curiosity prompt")

    # Generic performance/context fallback, designed to remain truthful under injected triggers.
    ctr = perf.get("ctr")
    views = perf.get("views")
    calls = perf.get("calls")
    offer = active[0] if active else None
    if ctr is not None and views is not None:
        body = (
            f"{owner}, quick check for {biz}: {views:,} views and {calls if calls is not None else '?'} calls "
            f"in the last {perf.get('window_days',30)} days, with {float(ctr)*100:.1f}% CTR. "
            f"{'Your active offer is ' + offer + '. ' if offer else ''}"
            f"I can use the current trigger to suggest one concrete improvement. Want me to?"
        )
        fact = f"{views:,} views and {float(ctr)*100:.1f}% CTR"
    else:
        body = f"{owner}, I have a new {kind.replace('_',' ')} signal for {biz}. Want me to turn it into one concrete next step?"
        fact = f"the {kind} signal"
    return body, "open_ended", _rationale(kind, fact)


def _customer_action(category, merchant, trigger, customer):
    kind = trigger.get("kind", "")
    p = trigger.get("payload", {}) or {}
    ident = _identity(merchant)
    biz = ident.get("name", "the business")
    cname = _name_for_customer(customer)
    lang = ((customer or {}).get("identity", {}) or {}).get("language_pref", "en")
    offers = _active_offers(merchant)

    if kind == "recall_due" and p.get("available_slots"):
        slots = p["available_slots"]
        first = slots[0].get("label", "")
        second = slots[1].get("label", "") if len(slots) > 1 else ""
        service = p.get("service_due", "your follow-up").replace("_", " ")
        price = next((x for x in offers if "₹" in x), None)
        price_text = f" {price}." if price else ""
        body = (
            f"Hi {cname}, {biz} here. Your {service} window is due"
            f" — we have {first}" + (f" or {second}" if second else "") +
            f" available.{price_text} Reply YES if you’d like us to hold a slot."
        )
        if "hi" in str(lang).lower():
            body = (
                f"Hi {cname}, {biz} here. Aapka {service} due hai — "
                f"{first}" + (f" ya {second}" if second else "") +
                f" available hai. Reply YES if you’d like us to hold a slot."
            )
        return body, "YES/STOP", _rationale(kind, f"the due window and available slot(s)")

    if kind == "customer_lapsed_hard":
        days = p.get("days_since_last_visit")
        focus = p.get("previous_focus")
        trial = _find_offer(merchant, "Trial") or _find_offer(merchant, "FREE")
        body = (
            f"Hi {cname}, {biz} here. It’s been about {days} days since your last visit — no pressure. "
            f"We can pick up with a session aligned to {focus.replace('_',' ')}"
            f"{' using ' + trial if trial else ''}. Reply YES if you’d like us to hold a trial spot."
        )
        return body, "YES/STOP", _rationale(kind, f"{days} days since the last visit")

    if kind == "chronic_refill_due" and p.get("molecule_list"):
        meds = ", ".join(p["molecule_list"])
        date = (p.get("stock_runs_out_iso") or "").split("T")[0]
        delivery = " Delivery to your saved address is available." if p.get("delivery_address_saved") else ""
        body = (
            f"Namaste {cname} — {biz} here. Your monthly medicines ({meds}) are due to run out around {date}.{delivery} "
            f"Reply CONFIRM if you want us to prepare the refill, or tell us what has changed."
        )
        return body, "CONFIRM/STOP", _rationale(kind, f"the medicine list and run-out date")

    if kind == "appointment_tomorrow":
        body = (
            f"Hi {cname}, {biz} here. Quick reminder: your appointment is tomorrow. "
            f"Reply YES to confirm, or tell us if the timing needs to change."
        )
        return body, "YES/STOP", _rationale(kind, "the appointment-tomorrow trigger")

    if kind in {"customer_lapsed_soft", "trial_followup"}:
        if kind == "trial_followup":
            opts = p.get("next_session_options") or []
            slot = opts[0].get("label") if opts else None
            body = (
                f"Hi {cname}, {biz} here. Following up on your recent trial"
                + (f" — the next option is {slot}." if slot else ".")
                + " Reply YES if you’d like us to reserve it."
            )
        else:
            body = (
                f"Hi {cname}, {biz} here. We haven’t seen you recently. "
                f"If you’d like to come back, I can help arrange a convenient next visit. Reply YES and we’ll take it from there."
            )
        return body, "YES/STOP", _rationale(kind, "the customer's relationship state")

    # Safe generic customer message: never invent a clinical/financial claim.
    body = f"Hi {cname}, {biz} here. We have a reminder related to your account. Reply YES and we’ll help with the next step."
    return body, "YES/STOP", _rationale(kind, "the customer-facing trigger")


def compose(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None) -> dict:
    """
    Returns: body, cta, send_as, suppression_key, rationale.
    Deterministic: no network calls, no randomness, no hidden state.
    """
    if customer is not None or trigger.get("scope") == "customer":
        body, cta, rationale = _customer_action(category, merchant, trigger, customer or {})
        send_as = "merchant_on_behalf"
    else:
        body, cta, rationale = _merchant_action(category, merchant, trigger)
        send_as = "vera"

    # Avoid accidental URL injection into WhatsApp body.
    body = body.replace("http://", "").replace("https://", "")
    return {
        "body": body.strip(),
        "cta": cta,
        "send_as": send_as,
        "suppression_key": trigger.get("suppression_key") or f"{trigger.get('kind','trigger')}:{merchant.get('merchant_id','merchant')}",
        "rationale": rationale,
    }
