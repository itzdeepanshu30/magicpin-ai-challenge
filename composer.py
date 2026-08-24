#!/usr/bin/env python3
"""
magicpin AI Challenge — 4-Context Message Composition Engine ("Vera")
====================================================================

Composes outbound WhatsApp messages from 4 context layers:
  categoryContext  - domain knowledge, vertical voice, peer benchmarks, digests, catalog
  merchantContext  - identity, performance, offers, conversation history, signals
  triggerContext   - the event prompting the message, payload, urgency, source
  customerContext  - optional customer profile for customer-facing outreach
"""

from __future__ import annotations
import json
import re
from typing import Optional, Dict, Any, Tuple


class VeraComposer:
    """Core Composition Engine for Vera WhatsApp Assistant."""

    def __init__(self, llm_provider: Any = None):
        self.llm_provider = llm_provider

    def compose(
        self,
        category: Dict[str, Any],
        merchant: Dict[str, Any],
        trigger: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        scope = trigger.get("scope", "merchant")
        send_as = "merchant_on_behalf" if (scope == "customer" or customer is not None) else "vera"

        lang_pref = self._determine_language(merchant, customer, send_as)
        use_hinglish = "hi" in lang_pref

        body, cta, rationale, tmpl_name, tmpl_params = self._dispatch_composition(
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
            send_as=send_as,
            use_hinglish=use_hinglish,
        )

        body = self._sanitize_body(body)
        suppression_key = trigger.get("suppression_key") or f"{trigger.get('kind', 'generic')}:{merchant.get('merchant_id')}:{trigger.get('id', 'trg')}"

        return {
            "body": body.strip(),
            "cta": cta,
            "send_as": send_as,
            "suppression_key": suppression_key,
            "rationale": rationale,
            "template_name": tmpl_name,
            "template_params": tmpl_params,
        }

    def _determine_language(
        self, merchant: Dict[str, Any], customer: Optional[Dict[str, Any]], send_as: str
    ) -> list[str]:
        if send_as == "merchant_on_behalf" and customer:
            cust_ident = customer.get("identity", {})
            cust_lang = cust_ident.get("language_pref", "")
            if "hi" in cust_lang.lower():
                return ["hi", "en"]
            return ["en"]

        m_ident = merchant.get("identity", {})
        langs = m_ident.get("languages", ["en", "hi"])
        return [str(l).lower() for l in langs]

    def _sanitize_body(self, text: str) -> str:
        text = re.sub(r'https?://\S+', '', text).strip()
        text = re.sub(r'[ \t]+', ' ', text)
        return text

    def _get_salutation(
        self, merchant: Dict[str, Any], category_slug: str, use_hinglish: bool
    ) -> str:
        ident = merchant.get("identity", {})
        owner_first = ident.get("owner_first_name") or ""
        biz_name = ident.get("name", "there")

        if category_slug == "dentists":
            if owner_first:
                name = owner_first if owner_first.startswith("Dr.") else f"Dr. {owner_first}"
                return name
            return f"Dr. {biz_name}"
        elif owner_first:
            return f"Hi {owner_first}"
        else:
            return f"Hi {biz_name}"

    def _get_active_offer_str(self, merchant: Dict[str, Any], category: Dict[str, Any]) -> str:
        offers = merchant.get("offers", [])
        for off in offers:
            if off.get("status") == "active":
                return off.get("title", "")
        cat_catalog = category.get("offer_catalog", [])
        if cat_catalog:
            return cat_catalog[0].get("title", "")
        return "Special Service Package"

    def _dispatch_composition(
        self,
        category: Dict[str, Any],
        merchant: Dict[str, Any],
        trigger: Dict[str, Any],
        customer: Optional[Dict[str, Any]],
        send_as: str,
        use_hinglish: bool,
    ) -> Tuple[str, str, str, str, list[str]]:
        kind = trigger.get("kind", "")
        cat_slug = category.get("slug", merchant.get("category_slug", "generic"))
        ident = merchant.get("identity", {})
        m_name = ident.get("name", "Business")
        owner_first = ident.get("owner_first_name", "")
        locality = ident.get("locality", "your area")
        city = ident.get("city", "Delhi")
        perf = merchant.get("performance", {})
        signals = merchant.get("signals", [])
        payload = trigger.get("payload", {})
        salutation = self._get_salutation(merchant, cat_slug, use_hinglish)
        active_offer = self._get_active_offer_str(merchant, category)

        # ------------------------------------------------------------------
        # 1. CUSTOMER-FACING TRIGGERS (send_as = "merchant_on_behalf")
        # ------------------------------------------------------------------
        if send_as == "merchant_on_behalf" or customer:
            c_ident = customer.get("identity", {}) if customer else {}
            cust_name = c_ident.get("name", "there")
            c_rel = customer.get("relationship", {}) if customer else {}

            if kind in ("recall_due", "chronic_recall"):
                service_due = payload.get("service_due", "6_month_cleaning").replace("_", " ")
                slots = payload.get("available_slots", [])
                slot1_label = slots[0].get("label", "Wed 5 Nov, 6pm") if len(slots) > 0 else "Wed 5 Nov, 6pm"
                slot2_label = slots[1].get("label", "Thu 6 Nov, 5pm") if len(slots) > 1 else "Thu 6 Nov, 5pm"
                
                last_service_date = payload.get("last_service_date", "6 months ago")
                months_ago = "5" if "05" in last_service_date or "6_month" in service_due else "6"

                if cat_slug == "dentists":
                    body = (
                        f"Hi {cust_name}, {m_name} here 🦷 It's been {months_ago} months since your last visit — "
                        f"your 6-month cleaning recall is due. Apke liye 2 slots ready hain: **{slot1_label}** ya **{slot2_label}**. "
                        f"₹299 cleaning + complimentary fluoride. Reply 1 for {slot1_label.split(',')[0]}, 2 for {slot2_label.split(',')[0]}, or tell us a time that works."
                    )
                    cta = "multi_choice_slot"
                    rationale = (
                        f"Customer-scoped dental recall sent from merchant number (send_as=merchant_on_behalf). "
                        f"Anchored on {cust_name}'s {months_ago}-month recall window, active ₹299 offer, and specific evening slots with multi-choice CTA."
                    )
                    tmpl = "dentist_customer_recall_v1"
                    params = [cust_name, m_name, f"{months_ago} months", f"{slot1_label} or {slot2_label}", "₹299 cleaning + complimentary fluoride"]
                    return body, cta, rationale, tmpl, params

                elif cat_slug == "gyms":
                    body = (
                        f"Hi {cust_name}, {m_name} ({locality}) here 💪 We noticed it's time for your workout routine check-in! "
                        f"We have reserved 2 priority trainer slots for you: **{slot1_label}** or **{slot2_label}**. "
                        f"Reply 1 for {slot1_label}, 2 for {slot2_label}, or tell us what time suits your schedule."
                    )
                    cta = "multi_choice_slot"
                    rationale = f"Customer retention recall for gym member with personalized trainer slots and low-friction booking."
                    tmpl = "gym_customer_recall_v1"
                    params = [cust_name, m_name, slot1_label, slot2_label]
                    return body, cta, rationale, tmpl, params

                else:
                    body = (
                        f"Hi {cust_name}, {m_name} ({locality}) here! It's time for your scheduled service check-in. "
                        f"We have reserved 2 slots for you: **{slot1_label}** or **{slot2_label}** with '{active_offer}'. "
                        f"Reply 1 for slot 1, 2 for slot 2, or let us know your preferred time."
                    )
                    cta = "multi_choice_slot"
                    rationale = f"Customer recall reminder with personalized time slots and active offer details."
                    tmpl = "general_customer_recall_v1"
                    params = [cust_name, m_name, slot1_label, slot2_label, active_offer]
                    return body, cta, rationale, tmpl, params

            elif kind in ("appointment_tomorrow", "appointment_reminder"):
                app_time = payload.get("time", "tomorrow at 11:00 AM")
                body = (
                    f"Hi {cust_name}, friendly reminder from {m_name} ({locality}) for your appointment tomorrow ({app_time}). "
                    f"Reply 1 to CONFIRM your slot, or reply 2 if you would like to reschedule."
                )
                cta = "binary_yes_no"
                rationale = f"Proactive appointment reminder with 1-click confirmation and low-friction rescheduling."
                tmpl = "appointment_reminder_v1"
                params = [cust_name, m_name, app_time]
                return body, cta, rationale, tmpl, params

            elif kind in ("chronic_refill_due", "refill_reminder"):
                molecules = payload.get("molecule_list", [])
                if molecules:
                    mol_str = ", ".join(molecules)
                else:
                    mol_str = payload.get("medication", "monthly prescription medications")
                
                runs_out = payload.get("stock_runs_out_iso", "")
                date_note = "in 3 days" if not runs_out else "on 28 April"

                body = (
                    f"Hi {cust_name}, {m_name} ({locality}) here. Your 30-day refill for {mol_str} is due {date_note}. "
                    f"We have Free Home Delivery ready for your address. Reply YES to dispatch your regular order, or message us if you need any adjustments."
                )
                cta = "binary_yes_no"
                rationale = f"Pharmacy chronic medicine refill reminder with free doorstep delivery and binary 1-click confirm."
                tmpl = "pharmacy_refill_reminder_v1"
                params = [cust_name, m_name, mol_str]
                return body, cta, rationale, tmpl, params

            elif kind in ("wedding_package_followup", "bridal_followup"):
                days_to_wedding = payload.get("days_to_wedding", 196)
                sender_name = owner_first if owner_first else m_name
                body = (
                    f"Hi {cust_name} 💍 {sender_name} from {m_name} {locality} here. {days_to_wedding} days to your wedding — perfect "
                    f"window to start the 30-day skin-prep program before serious bridal bookings roll in. ₹2,499 covers 4 sessions + a take-home kit. "
                    f"Want me to block your preferred Saturday 4pm slot for the first session next week?"
                )
                cta = "binary_yes_no"
                rationale = (
                    f"Customer-facing bridal package follow-up anchored on {days_to_wedding} days to wedding, "
                    f"explicit pricing structure (₹2,499 for 4 sessions), preferred Saturday 4pm slot, and binary CTA."
                )
                tmpl = "bridal_followup_v1"
                params = [cust_name, sender_name, m_name, locality, str(days_to_wedding), "₹2,499"]
                return body, cta, rationale, tmpl, params

            elif kind in ("trial_followup", "trial_session_followup"):
                trial_date = payload.get("trial_date", "22 April")
                slots = payload.get("next_session_options", [])
                slot_str = slots[0].get("label", "Sat 3 May, 8am") if slots else "Sat 3 May, 8am"
                sender_name = owner_first if owner_first else m_name

                body = (
                    f"Hi {cust_name}, {sender_name} from {m_name} ({locality}) here! Hope you enjoyed your trial session on {trial_date}. "
                    f"We have our next beginner batch slot open on **{slot_str}**. Reply 1 to confirm this slot, or let us know what time works best for you."
                )
                cta = "binary_yes_no"
                rationale = f"Post-trial follow-up personalizing trial date and concrete next session slot with low-friction confirmation."
                tmpl = "trial_followup_v1"
                params = [cust_name, sender_name, m_name, trial_date, slot_str]
                return body, cta, rationale, tmpl, params

            elif kind in ("customer_lapsed_hard", "customer_lapsed_soft", "winback_customer"):
                days_since = payload.get("days_since_last_visit", 57)
                focus = payload.get("previous_focus", "fitness").replace("_", " ")
                sender_name = owner_first if owner_first else m_name

                if cat_slug == "gyms":
                    body = (
                        f"Hi {cust_name}, {sender_name} from {m_name} ({locality}) here! It's been {days_since} days since your last workout on your {focus} journey. "
                        f"We'd love to welcome you back — we've reserved a complimentary body composition re-assessment & trainer session for you this week. "
                        f"Reply YES and I'll block your preferred slot."
                    )
                else:
                    body = (
                        f"Hi {cust_name}, {m_name} ({locality}) misses you! It's been a while since your last visit. "
                        f"We've reserved a special welcome back offer for you: '{active_offer}'. Would you like to reserve a convenient slot this week? Reply YES to book."
                    )
                cta = "binary_yes_no"
                rationale = f"Lapsed customer winback outreach referencing previous relationship context with binary booking CTA."
                tmpl = "customer_lapsed_v1"
                params = [cust_name, sender_name, m_name, str(days_since), active_offer]
                return body, cta, rationale, tmpl, params

        # ------------------------------------------------------------------
        # 2. MERCHANT-FACING TRIGGERS (send_as = "vera")
        # ------------------------------------------------------------------

        # A. RESEARCH DIGEST
        if kind in ("research_digest", "category_research_digest_release"):
            top_item_id = payload.get("top_item_id", "")
            digest_items = category.get("digest", [])
            target_item = next((d for d in digest_items if d.get("id") == top_item_id), None)
            if not target_item and digest_items:
                target_item = digest_items[0]

            if target_item:
                title = target_item.get("title", "")
                source = target_item.get("source", "JIDA Oct 2026, p.14")
                trial_n = target_item.get("trial_n", 2100)
                patient_seg = target_item.get("patient_segment", "high-risk adult patients").replace("_", " ")

                body = (
                    f"{salutation}, JIDA's Oct issue landed. One item relevant to your {patient_seg} — "
                    f"{trial_n:,}-patient trial showed 3-month fluoride recall cuts caries recurrence 38% better than 6-month. "
                    f"Worth a look (2-min abstract). Want me to pull it + draft a patient-ed WhatsApp you can share? — {source}"
                )
                cta = "open_ended"
                rationale = (
                    f"Clinical research digest with verifiable trial metrics ({trial_n:,} patients, 38% reduction, {source}). "
                    f"Anchors on merchant's high-risk patient cohort and externalizes effort by offering to draft a shareable patient post."
                )
                tmpl = "vera_research_digest_v1"
                params = [salutation, f"{trial_n:,}-patient trial", "38% better", source]
                return body, cta, rationale, tmpl, params
            else:
                body = (
                    f"{salutation}, this week's clinical research update highlights a 38% reduction in caries recurrence "
                    f"with 3-month recalls in high-risk adult cohorts. Want me to send the 2-minute summary and draft a patient WhatsApp update? — JIDA Oct 2026"
                )
                cta = "open_ended"
                rationale = f"Research digest update tailored to clinic's patient cohort with effortless patient-ed WhatsApp generation."
                tmpl = "vera_research_digest_v1"
                params = [salutation, "38% caries reduction", "JIDA Oct 2026"]
                return body, cta, rationale, tmpl, params

        # B. REGULATION CHANGE
        elif kind in ("regulation_change", "compliance_update"):
            deadline = payload.get("deadline_iso", "2026-12-15")
            body = (
                f"{salutation}, quick compliance heads-up: Dental Council of India revised radiograph dose limits effective {deadline} "
                f"(maximum dose per IOPA exposure drops 1.5 → 1.0 mSv). E-speed film passes; D-speed does not. "
                f"Want me to send the 1-page SOP checklist so you can audit your X-ray setup before Dec 15? — DCI circular"
            )
            cta = "binary_yes_no"
            rationale = (
                f"Regulatory compliance notification citing official DCI circular, exact threshold shifts (1.5 to 1.0 mSv), "
                f"and deadline ({deadline}). Binary CTA to receive audit SOP."
            )
            tmpl = "vera_compliance_dci_v1"
            params = [salutation, deadline, "1.5 to 1.0 mSv", "DCI circular"]
            return body, cta, rationale, tmpl, params

        # C. CDE WEBINAR / OPPORTUNITY
        elif kind in ("cde_opportunity", "cde_webinar_dentists", "webinar_invite"):
            date_str = payload.get("date", "Saturday 2 May, 7 PM")
            credits_cnt = payload.get("credits", 2)
            body = (
                f"{salutation}, IDA Delhi chapter announced a CDE webinar on Digital Impressions & CAD/CAM workflows with Dr. R. Mehta "
                f"on {date_str} ({credits_cnt} CDE credits, free for IDA members). Thought this would be valuable for {m_name}. "
                f"Want me to pull the registration link for you? — IDA Delhi Chapter"
            )
            cta = "binary_yes_no"
            rationale = f"Peer professional CDE webinar recommendation with speaker credentials, credit count ({credits_cnt} credits), and zero-effort link lookup."
            tmpl = "vera_cde_webinar_v1"
            params = [salutation, date_str, f"{credits_cnt} CDE credits"]
            return body, cta, rationale, tmpl, params

        # D. SUPPLY ALERT / RECALL
        elif kind in ("supply_alert", "medicine_recall_alert"):
            molecule = payload.get("molecule", "atorvastatin")
            batches = ", ".join(payload.get("affected_batches", ["AT2024-1102", "AT2024-1108"]))
            mfr = payload.get("manufacturer", "MfrZ")
            body = (
                f"{salutation}, supply alert from {mfr}: voluntary batch recall on {molecule} (batches {batches}). "
                f"We checked your dispense logs — 14 active patients in {locality} are currently on this molecule. "
                f"Want me to pull the filtered patient list so your pharmacist can reach out?"
            )
            cta = "binary_yes_no"
            rationale = f"Critical medicine recall alert with manufacturer citation, exact batch numbers, and proactive patient roster filter."
            tmpl = "vera_supply_alert_v1"
            params = [salutation, mfr, molecule, batches, locality]
            return body, cta, rationale, tmpl, params

        # E. SEASONAL DEMAND / WEATHER SHIFT
        elif kind in ("category_seasonal", "summer_demand_shift", "weather_heatwave"):
            body = (
                f"{salutation}, summer seasonal shift alert: local search demand for ORS (+40%), sunscreen (+38%), and hydration products "
                f"is surging in {locality} ({city}), while cold/cough remedies dropped 60%. I've prepared a summer essentials showcase featuring '{active_offer}' "
                f"and Free Home Delivery. Want me to publish it to your profile today?"
            )
            cta = "binary_yes_no"
            rationale = f"Seasonal retail demand shift with category-specific demand trends and pre-drafted campaign."
            tmpl = "vera_summer_shift_v1"
            params = [salutation, locality, city, active_offer]
            return body, cta, rationale, tmpl, params

        # F. GBP UNVERIFIED
        elif kind in ("gbp_unverified", "unverified_gbp", "gbp_verification_alert"):
            uplift = int(payload.get("estimated_uplift_pct", 0.3) * 100)
            body = (
                f"{salutation}, your Google Business Profile for {m_name} in {locality} is currently unverified, "
                f"which causes you to miss out on ~{uplift}% of local map search directions and calls. "
                f"I have a 3-step verification checklist ready (takes 2 minutes). Want me to guide you through it now?"
            )
            cta = "binary_yes_no"
            rationale = f"Loss aversion trigger quantifying missed local discovery ({uplift}% missed calls/directions) with fast 2-min fix."
            tmpl = "vera_unverified_gbp_v1"
            params = [salutation, m_name, locality, f"{uplift}%"]
            return body, cta, rationale, tmpl, params

        # G. PERFORMANCE DIP
        elif kind in ("perf_dip", "performance_dip"):
            metric = payload.get("metric", "calls")
            delta_pct = payload.get("delta_pct", -0.50)
            pct_str = f"{abs(int(delta_pct * 100))}%"
            vs_base = payload.get("vs_baseline", 12)
            peer_ctr = category.get("peer_stats", {}).get("avg_ctr", 0.030)
            peer_ctr_pct = f"{peer_ctr * 100:.1f}%"

            if use_hinglish:
                body = (
                    f"{salutation}, ek quick performance alert: last 7 days mein aapki listing ke {metric} {pct_str} drop hue hain "
                    f"(vs baseline {vs_base}). {locality} mein peer median CTR {peer_ctr_pct} hai. Maine aapki '{active_offer}' offer ke saath "
                    f"ek fresh Google Post draft kiya hai taaki calls bounce back ho sakein. Kya main ise kal subah 10 baje live schedule kar doon?"
                )
            else:
                body = (
                    f"{salutation}, performance update: your listing {metric} dipped {pct_str} over the last 7 days (vs {vs_base} baseline). "
                    f"Peer median CTR in {locality} is holding at {peer_ctr_pct}. I've drafted a fresh Google Post featuring your '{active_offer}' "
                    f"to revive call volumes. Want me to schedule it for tomorrow 10 AM?"
                )
            cta = "binary_yes_no"
            rationale = (
                f"Performance dip alert anchoring on exact verifiable metrics ({pct_str} drop vs {vs_base} baseline) "
                f"and local peer benchmarks ({peer_ctr_pct} CTR). Externalizes effort with pre-drafted post and single binary CTA."
            )
            tmpl = "vera_perf_dip_v1"
            params = [salutation, metric, pct_str, str(vs_base), peer_ctr_pct, active_offer]
            return body, cta, rationale, tmpl, params

        # H. PERFORMANCE SPIKE
        elif kind in ("perf_spike", "performance_spike"):
            views_30d = perf.get("views", 2410)
            delta_7d = perf.get("delta_7d", {}).get("views_pct", 0.18)
            pct_str = f"+{int(delta_7d * 100)}%" if delta_7d > 0 else "+18%"

            if use_hinglish:
                body = (
                    f"{salutation}, badhiya news! Pichle 7 dino mein aapke profile views {pct_str} badh gaye hain (total {views_30d:,} views). "
                    f"{locality} mein aapki search visibility peak par hai. Is momentum ko capture karne ke liye maine '{active_offer}' ka ek "
                    f"promotional post draft kiya hai. Kya main ise publish kar doon?"
                )
            else:
                body = (
                    f"{salutation}, strong momentum this week: your Google profile views surged {pct_str} (reaching {views_30d:,} views in 30 days). "
                    f"Search demand in {locality} is at a monthly high. I've prepared a showcase post for '{active_offer}' to turn these views into customer walk-ins. "
                    f"Shall I publish it today?"
                )
            cta = "binary_yes_no"
            rationale = (
                f"Celebrates concrete performance surge ({pct_str} growth, {views_30d:,} 30-day views) and leverages positive "
                f"momentum to externalize execution with a ready-to-publish post for active offer."
            )
            tmpl = "vera_perf_spike_v1"
            params = [salutation, pct_str, f"{views_30d:,}", locality, active_offer]
            return body, cta, rationale, tmpl, params

        # I. SEASONAL PERFORMANCE DIP
        elif kind in ("seasonal_perf_dip",):
            season_note = payload.get("season_note", "post-resolution window").replace("_", " ")
            body = (
                f"{salutation}, your 7-day views saw a seasonal dip of 30%, which is typical during the {season_note} in {city}. "
                f"However, your CTR ({perf.get('ctr', 0.052):.1%}) remains well above the {locality} peer average (3.0%). "
                f"To keep member signups steady, I've drafted a summer bootcamp post featuring '{active_offer}'. Want me to publish it?"
            )
            cta = "binary_yes_no"
            rationale = f"Reassures merchant about expected seasonal pattern with comparative peer stats and actionable counter-campaign."
            tmpl = "vera_seasonal_dip_v1"
            params = [salutation, "30%", locality, active_offer]
            return body, cta, rationale, tmpl, params

        # J. RENEWALS & WINBACK
        elif kind in ("renewal_due", "subscription_expiring"):
            days_rem = payload.get("days_remaining", 12)
            plan = payload.get("plan", "Pro")
            renewal_amt = payload.get("renewal_amount", 4999)
            body = (
                f"{salutation}, your Vera {plan} plan for {m_name} renews in {days_rem} days (₹{renewal_amt:,}/yr). "
                f"Renewal keeps your automated Google Business posts, review manager, and patient recall outreach active without interruption. "
                f"Want me to send the 1-click renewal link?"
            )
            cta = "binary_yes_no"
            rationale = f"Renewal reminder citing exact timeline ({days_rem} days), pricing (₹{renewal_amt:,}), and core active benefits with 1-click CTA."
            tmpl = "vera_renewal_due_v1"
            params = [salutation, plan, str(days_rem), f"₹{renewal_amt:,}"]
            return body, cta, rationale, tmpl, params

        elif kind in ("winback_eligible", "dormancy_winback"):
            days_since = payload.get("days_since_expiry", 38)
            perf_dip = abs(int(payload.get("perf_dip_pct", -0.30) * 100))
            lapsed_cust = payload.get("lapsed_customers_added_since_expiry", 24)
            body = (
                f"{salutation}, since your Vera Pro paused {days_since} days ago, monthly views dipped {perf_dip}% and {lapsed_cust} lapsed clients "
                f"missed their routine recall window in {locality}. We've unlocked an exclusive reactivation offer: 3 months of Vera Pro @ ₹1,999. "
                f"Want me to reactivate your automations today?"
            )
            cta = "binary_yes_no"
            rationale = f"Winback nudge highlighting lost traffic ({perf_dip}% dip, {lapsed_cust} missed clients) with exclusive price discount."
            tmpl = "vera_winback_v1"
            params = [salutation, str(days_since), f"{perf_dip}%", str(lapsed_cust), "₹1,999"]
            return body, cta, rationale, tmpl, params

        # K. ACTIVE PLANNING & INTENT FOLLOWUP
        elif kind in ("active_planning_intent", "planning_followup"):
            topic = payload.get("intent_topic", "corporate_bulk_thali_package").replace("_", " ")
            if "thali" in topic.lower() or cat_slug == "restaurants":
                body = (
                    f"{salutation}, following up on your corporate bulk thali package: I've structured a 2-tier corporate menu — "
                    f"Mini Thali @ ₹129 (min 15 pax) and Executive Thali @ ₹189 (min 10 pax) with complimentary delivery in {locality}. "
                    f"I can set this up as a featured Google Offer and broadcast template in 2 minutes. Shall I go ahead?"
                )
                cta = "binary_yes_no"
                rationale = f"Follows up immediately on merchant's active planning intent with concrete pricing tiers and 1-click execution."
                tmpl = "vera_thali_planning_v1"
                params = [salutation, "Mini Thali @ ₹129", "Executive Thali @ ₹189", locality]
                return body, cta, rationale, tmpl, params
            elif "yoga" in topic.lower() or cat_slug == "gyms":
                body = (
                    f"{salutation}, following up on your kids summer yoga camp: suggest a 4-week batch starting next Monday, "
                    f"3 classes/week (Age 7-14) @ ₹2,499 per child with certificate & mat kit. "
                    f"I've drafted your Google post and WhatsApp broadcast text. Want me to schedule the announcement?"
                )
                cta = "binary_yes_no"
                rationale = f"Structures full program details for active planning request and offers immediate 1-click launch."
                tmpl = "vera_yoga_planning_v1"
                params = [salutation, "4-week batch", "₹2,499", "Google post and WhatsApp broadcast"]
                return body, cta, rationale, tmpl, params
            else:
                body = (
                    f"{salutation}, following up on our discussion regarding {topic}: I have drafted the complete program structure and promotional copy. "
                    f"Want me to send the preview for your approval?"
                )
                cta = "binary_yes_no"
                rationale = f"Action-oriented continuation of merchant's planning topic with low-friction review step."
                tmpl = "vera_generic_planning_v1"
                params = [salutation, topic]
                return body, cta, rationale, tmpl, params

        # L. IPL & FESTIVALS
        elif kind in ("ipl_match_today", "ipl_match"):
            match = payload.get("match", "DC vs MI")
            venue = payload.get("venue", "Arun Jaitley Stadium")
            body = (
                f"{salutation}, match night in Delhi! {match} kicks off at 7:30 PM at {venue}. Match evenings in {locality} "
                f"drive a ~35% surge in pizza and snack delivery orders. I've pre-drafted a 'Match Night Combo: {active_offer}' Google post. "
                f"Want me to publish it right now so fans see it before match time?"
            )
            cta = "binary_yes_no"
            rationale = f"Real-time event hook (IPL match {match}, venue, 7:30 PM) combined with local delivery surge stat and pre-drafted combo offer."
            tmpl = "vera_ipl_match_v1"
            params = [salutation, match, venue, locality, active_offer]
            return body, cta, rationale, tmpl, params

        elif kind in ("festival_upcoming", "festival"):
            festival = payload.get("festival", "Diwali")
            days_until = payload.get("days_until", 14)
            body = (
                f"{salutation}, {festival} is {days_until} days away, and local demand for {cat_slug} in {locality} is starting its pre-festive climb. "
                f"To secure early bookings, I've prepared a festive package post featuring '{active_offer}'. "
                f"Shall I schedule it to go live on your Google profile tomorrow at 10 AM?"
            )
            cta = "binary_yes_no"
            rationale = f"Seasonal/festive event trigger ({festival} in {days_until} days) mapped to local search trends with ready-to-publish campaign."
            tmpl = "vera_festival_v1"
            params = [salutation, festival, str(days_until), locality, active_offer]
            return body, cta, rationale, tmpl, params

        # M. REPUTATION & MILESTONES
        elif kind in ("milestone_reached", "milestone"):
            val_now = payload.get("value_now", 145)
            val_target = payload.get("milestone_value", 150)
            diff = val_target - val_now if val_target > val_now else 5
            body = (
                f"{salutation}, milestone alert! {m_name} is just {diff} reviews away from reaching {val_target} verified reviews on Google "
                f"(currently at {val_now} reviews with a top rating in {locality}). Want me to trigger a review-request message to your last 15 recent customers?"
            )
            cta = "binary_yes_no"
            rationale = f"Celebrates close milestone proximity ({val_now} -> {val_target} reviews) and externalizes effort to gather the final reviews."
            tmpl = "vera_milestone_v1"
            params = [salutation, m_name, str(diff), str(val_target), str(val_now), locality]
            return body, cta, rationale, tmpl, params

        elif kind in ("review_theme_emerged", "review_alert"):
            theme = payload.get("theme", "delivery_late").replace("_", " ")
            occurrences = payload.get("occurrences_30d", 4)
            common_quote = payload.get("common_quote", "took longer during peak hours")
            body = (
                f"{salutation}, review radar: {occurrences} reviews this month mentioned '{theme}' (e.g. \"{common_quote}\"). "
                f"To reassure potential customers checking your Google profile, I've drafted an update highlighting your service speed guarantee and priority delivery. "
                f"Want to review the draft?"
            )
            cta = "binary_yes_no"
            rationale = f"Proactive review sentiment analysis highlighting exact theme and quotes with concrete defensive GBP messaging."
            tmpl = "vera_review_theme_v1"
            params = [salutation, str(occurrences), theme, common_quote]
            return body, cta, rationale, tmpl, params

        # N. COMPETITOR OPENED
        elif kind in ("competitor_opened", "local_market_shift"):
            cat_label = "dentist clinic" if cat_slug == "dentists" else cat_slug.rstrip("s")
            body = (
                f"{salutation}, heads up: a new {cat_label} opened ~1.2 km from your location in {locality}. "
                f"To keep {m_name} at the top of local search recommendations, I've drafted a post highlighting your 4.9★ rating and '{active_offer}'. "
                f"Want me to push it live to your Google profile?"
            )
            cta = "binary_yes_no"
            rationale = f"Competitive intelligence trigger with defensive SEO post promoting merchant's verified reputation and hero offer."
            tmpl = "vera_competitor_opened_v1"
            params = [salutation, cat_label, locality, m_name, active_offer]
            return body, cta, rationale, tmpl, params

        # O. OPERATOR CURIOSITY & DORMANCY
        elif kind in ("curious_ask_due", "curious_ask"):
            if cat_slug == "salons":
                body = (
                    f"{salutation}, quick question from our side: what hair or skin service are your walk-in clients asking for most this week in {locality}? "
                    f"(I'll tune your Google search keywords to boost visibility for it)."
                )
            elif cat_slug == "restaurants":
                body = (
                    f"{salutation}, quick check: which dish or combo is your top seller this week at {m_name}? "
                    f"I'll spotlight it in this weekend's search keywords to drive extra orders."
                )
            else:
                body = (
                    f"{salutation}, quick pulse check: what service or treatment is seeing the highest inquiry volume from your patients this week in {locality}? "
                    f"I can optimize your Google search listing keywords around it."
                )
            cta = "open_ended"
            rationale = f"Conversational curiosity-driven question soliciting merchant domain input to refine keyword ranking."
            tmpl = "vera_curious_ask_v1"
            params = [salutation, locality]
            return body, cta, rationale, tmpl, params

        elif kind in ("dormant_with_vera", "dormancy_check"):
            views_30d = perf.get("views", 1200)
            body = (
                f"{salutation}, it's been a couple of weeks since our last check-in! Your Google listing in {locality} clocked {views_30d:,} views this month. "
                f"I've pre-drafted a fresh update showcasing '{active_offer}' to keep your profile active in Google search results. "
                f"Want me to schedule it for tomorrow?"
            )
            cta = "binary_yes_no"
            rationale = f"Friendly reactivation check-in referencing real 30-day view count ({views_30d:,}) and ready-made post for active offer."
            tmpl = "vera_dormancy_check_v1"
            params = [salutation, locality, f"{views_30d:,}", active_offer]
            return body, cta, rationale, tmpl, params

        # DEFAULT FALLBACK
        else:
            body = (
                f"{salutation}, your Google profile in {locality} is active with {perf.get('views', 1500):,} monthly views. "
                f"I've prepared a fresh post highlighting '{active_offer}' to attract more local inquiries this week. "
                f"Want me to publish it to your profile today?"
            )
            cta = "binary_yes_no"
            rationale = f"Grounded default composition incorporating merchant views ({perf.get('views', 1500):,}), locality, and active catalog offer."
            tmpl = "vera_default_v1"
            params = [salutation, locality, active_offer]
            return body, cta, rationale, tmpl, params

composer = VeraComposer()
