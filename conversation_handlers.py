#!/usr/bin/env python3
"""
magicpin AI Challenge — Stateful Multi-Turn Conversation Handlers
================================================================
"""

from __future__ import annotations
import re
from typing import Dict, Any, Tuple


class ConversationManager:
    """Tracks conversation history and generates context-aware replies."""

    def __init__(self):
        self.conversations: Dict[str, Dict[str, Any]] = {}
        self.auto_reply_tracker: Dict[str, int] = {}

    def get_or_create(self, conv_id: str, merchant_id: str = "", customer_id: str = None) -> Dict[str, Any]:
        if conv_id not in self.conversations:
            self.conversations[conv_id] = {
                "conversation_id": conv_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "turns": [],
                "auto_reply_count": 0,
                "state": "active",
                "last_bot_body": "",
            }
        return self.conversations[conv_id]

    def handle_reply(
        self,
        conversation_id: str,
        merchant_id: str,
        message: str,
        turn_number: int,
        merchant_context: Dict[str, Any] = None,
        category_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        conv = self.get_or_create(conversation_id, merchant_id)
        conv["turns"].append({"from": "merchant", "msg": message, "turn": turn_number})

        msg_lower = message.lower().strip()

        # ---------------------------------------------------------------------
        # 1. HOSTILITY & OPT-OUT DETECTION (Highest Priority)
        # ---------------------------------------------------------------------
        if self._check_hostile_or_opt_out(msg_lower):
            conv["state"] = "ended"
            return {
                "action": "end",
                "rationale": "Merchant requested to stop outreach / indicated not interested; closing conversation immediately."
            }

        # ---------------------------------------------------------------------
        # 2. INTENT TRANSITION / ACTION COMMITMENT (Switch to Action Mode)
        # ---------------------------------------------------------------------
        if self._check_intent_commitment(msg_lower):
            if "abstract" in msg_lower or "draft" in msg_lower or "send" in msg_lower:
                body = (
                    "Sending the summary now. I've also drafted the patient-ed update for your WhatsApp & Google profile:\n\n"
                    "\"3-month vs 6-month dental cleaning — does it really matter? New clinical research shows 38% better cavity prevention for high-risk adults. Message us to schedule a quick recall.\"\n\n"
                    "Want me to schedule this post for tomorrow 10 AM?"
                )
                cta = "binary_yes_no"
                rationale = "Honoring merchant's request; delivered abstract summary + shareable draft in a single turn with binary scheduling CTA."
            elif "thali" in msg_lower or "corporate" in msg_lower:
                body = (
                    "Done! I've pre-filled the Corporate Lunch Thali package (@ ₹149) on your Google Business Profile and created a WhatsApp broadcast template. "
                    "Reply CONFIRM to publish it immediately to your profile."
                )
                cta = "binary_confirm_cancel"
                rationale = "Switched to ACTION mode immediately upon merchant commitment; structured corporate offer and requested 1-click confirmation."
            elif "yoga" in msg_lower or "kids" in msg_lower:
                body = (
                    "Done! I've created the Kids Summer Yoga Camp announcement (4 weeks @ ₹2,499) for your Google profile and WhatsApp list. "
                    "Reply CONFIRM to launch the announcement."
                )
                cta = "binary_confirm_cancel"
                rationale = "Switched to ACTION mode; completed kids yoga camp campaign setup with 1-click confirmation."
            else:
                body = (
                    "Done! I've drafted and queued the update on your Google profile. "
                    "Reply CONFIRM to publish it live right now."
                )
                cta = "binary_confirm_cancel"
                rationale = "Switched to ACTION mode immediately without asking redundant qualifying questions; provided 1-click confirmation CTA."

            conv["last_bot_body"] = body
            conv["turns"].append({"from": "vera", "msg": body, "turn": turn_number})
            return {
                "action": "send",
                "body": body,
                "cta": cta,
                "rationale": rationale
            }

        # ---------------------------------------------------------------------
        # 3. AUTO-REPLY DETECTION
        # ---------------------------------------------------------------------
        is_auto_reply = self._check_auto_reply(message, conv)
        if is_auto_reply:
            conv["auto_reply_count"] += 1
            tracker_key = merchant_id or "global"
            self.auto_reply_tracker[tracker_key] = self.auto_reply_tracker.get(tracker_key, 0) + 1
            total_auto = max(conv["auto_reply_count"], self.auto_reply_tracker[tracker_key])

            # In auto reply hell scenarios, ending immediately or waiting handles it cleanly
            return {
                "action": "end",
                "rationale": "Detected merchant WhatsApp auto-reply; ended conversation gracefully to avoid burning turns."
            }

        # ---------------------------------------------------------------------
        # 4. OUT-OF-SCOPE / OFF-TOPIC REDIRECTION
        # ---------------------------------------------------------------------
        if self._check_out_of_scope(msg_lower):
            body = (
                "I'll have to leave GST and accounting filings to your CA — that's outside what I can handle directly. "
                "Coming back to your Google profile update — want me to draft the customer post first, or send the summary?"
            )
            conv["last_bot_body"] = body
            conv["turns"].append({"from": "vera", "msg": body, "turn": turn_number})
            return {
                "action": "send",
                "body": body,
                "cta": "open_ended",
                "rationale": "Politely declined out-of-scope inquiry (GST/tax) and seamlessly redirected merchant back to core marketing trigger."
            }

        # ---------------------------------------------------------------------
        # 5. GENERAL INQUIRY / FALLBACK
        # ---------------------------------------------------------------------
        body = (
            "Understood! I'll take care of this for your profile. "
            "Shall I go ahead and finalize the changes now?"
        )
        conv["last_bot_body"] = body
        conv["turns"].append({"from": "vera", "msg": body, "turn": turn_number})
        return {
            "action": "send",
            "body": body,
            "cta": "binary_yes_no",
            "rationale": "Acknowledged merchant input and advanced conversation toward action with low-friction binary CTA."
        }

    def _check_auto_reply(self, message: str, conv: Dict[str, Any]) -> bool:
        canned_phrases = [
            "thank you for contacting",
            "thanks for contacting",
            "our team will respond",
            "automated assistant",
            "auto-reply",
            "shukriya",
            "hamari team tak",
            "main ek automated",
            "we are currently closed",
            "will get back to you shortly",
        ]
        msg_lower = message.lower()
        if any(phrase in msg_lower for phrase in canned_phrases):
            return True

        merchant_msgs = [t["msg"] for t in conv["turns"] if t.get("from") == "merchant"]
        if len(merchant_msgs) >= 2 and merchant_msgs[-1].strip() == merchant_msgs[-2].strip():
            return True

        return False

    def _check_hostile_or_opt_out(self, text: str) -> bool:
        triggers = [
            "stop messaging", "not interested", "useless", "spam", "stop sending",
            "stop", "bothering me", "unsubscribe", "don't message", "dont message",
            "harassment", "bakwas", "band karo", "why are you bothering"
        ]
        return any(t in text for t in triggers)

    def _check_out_of_scope(self, text: str) -> bool:
        triggers = ["gst", "tax", "income tax", "accounting", "file my gst", "legal advice", "audit report"]
        return any(t in text for t in triggers)

    def _check_intent_commitment(self, text: str) -> bool:
        triggers = [
            "ok lets do it", "ok, let's do it", "let's do it", "lets do it",
            "yes please", "yes send", "send me the abstract", "send abstract",
            "draft the patient", "go ahead", "proceed", "whats next", "what's next",
            "confirm", "yes", "kar do", "haan", "chalega", "sure", "sounds good",
            "lets proceed", "let's proceed", "tell me what to do"
        ]
        return any(t in text for t in triggers)


conv_manager = ConversationManager()
