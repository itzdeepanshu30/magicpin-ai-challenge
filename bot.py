#!/usr/bin/env python3
"""
magicpin AI Challenge — Vera Merchant Assistant Server
======================================================

Exposes the 5 required HTTP REST endpoints:
  GET  /v1/healthz   - Liveness probe & loaded context counts
  GET  /v1/metadata  - Bot and team metadata
  POST /v1/context   - Idempotent context ingestion with versioning
  POST /v1/tick      - Proactive outbound message composition
  POST /v1/reply     - Stateful multi-turn conversation handler
"""

from __future__ import annotations
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from composer import composer
from conversation_handlers import conv_manager

app = FastAPI(title="magicpin AI Assistant — Vera", version="1.0.0")
START_TIME = time.time()

# In-memory storage for contexts: (scope, context_id) -> {"version": int, "payload": dict}
contexts: Dict[tuple[str, str], Dict[str, Any]] = {}
suppressed_keys: set[str] = set()


@app.get("/v1/healthz")
async def healthz():
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        if scope in counts:
            counts[scope] += 1
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": counts,
    }


@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Deepanshu Singhal",
        "team_members": ["Deepanshu Singhal"],
        "model": "gemini-3.7-flash",
        "approach": "Deterministic 4-context composition framework with vertical voice modulation, specificity anchors, and stateful multi-turn intent routing",
        "contact_email": "deepanshusinghal509@gmail.com",
        "version": "1.0.0",
        "submitted_at": "2026-04-26T08:00:00Z",
    }


class ContextRequest(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


@app.post("/v1/context")
async def push_context(body: ContextRequest):
    if body.scope not in ("category", "merchant", "customer", "trigger"):
        return {"accepted": False, "reason": "invalid_scope", "details": f"Unknown scope: {body.scope}"}

    key = (body.scope, body.context_id)
    cur = contexts.get(key)

    if cur and cur["version"] > body.version:
        # 409 stale version
        return {
            "accepted": False,
            "reason": "stale_version",
            "current_version": cur["version"],
        }

    # Store or replace atomically (idempotent for equal version, updates for higher version)
    contexts[key] = {
        "version": body.version,
        "payload": body.payload,
    }

    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": datetime.utcnow().isoformat() + "Z",
    }


class TickRequest(BaseModel):
    now: str
    available_triggers: List[str] = []


@app.post("/v1/tick")
async def tick(body: TickRequest):
    actions = []

    for trg_id in body.available_triggers:
        trg_ctx = contexts.get(("trigger", trg_id))
        if not trg_ctx:
            continue
        trg_payload = trg_ctx.get("payload", {})

        merchant_id = trg_payload.get("merchant_id")
        m_ctx = contexts.get(("merchant", merchant_id)) if merchant_id else None
        m_payload = m_ctx.get("payload", {}) if m_ctx else {}

        cat_slug = m_payload.get("category_slug") or trg_payload.get("payload", {}).get("category") or "dentists"
        c_ctx = contexts.get(("category", cat_slug))
        c_payload = c_ctx.get("payload", {}) if c_ctx else {}

        customer_id = trg_payload.get("customer_id")
        cust_ctx = contexts.get(("customer", customer_id)) if customer_id else None
        cust_payload = cust_ctx.get("payload", {}) if cust_ctx else None

        if not m_payload:
            continue

        supp_key = trg_payload.get("suppression_key") or f"{trg_payload.get('kind')}:{merchant_id}"
        if supp_key in suppressed_keys:
            continue

        composed = composer.compose(
            category=c_payload,
            merchant=m_payload,
            trigger=trg_payload,
            customer=cust_payload,
        )

        conv_id = f"conv_{merchant_id}_{trg_id}"

        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed["send_as"],
            "trigger_id": trg_id,
            "template_name": composed["template_name"],
            "template_params": composed["template_params"],
            "body": composed["body"],
            "cta": composed["cta"],
            "suppression_key": composed["suppression_key"],
            "rationale": composed["rationale"],
        })

    return {"actions": actions}


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: str
    turn_number: int


@app.post("/v1/reply")
async def reply(body: ReplyRequest):
    m_ctx = contexts.get(("merchant", body.merchant_id)) if body.merchant_id else None
    m_payload = m_ctx.get("payload", {}) if m_ctx else {}

    cat_slug = m_payload.get("category_slug", "dentists")
    c_ctx = contexts.get(("category", cat_slug))
    c_payload = c_ctx.get("payload", {}) if c_ctx else {}

    result = conv_manager.handle_reply(
        conversation_id=body.conversation_id,
        merchant_id=body.merchant_id or "",
        message=body.message,
        turn_number=body.turn_number,
        merchant_context=m_payload,
        category_context=c_payload,
    )
    return result


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("bot:app", host="0.0.0.0", port=port)
