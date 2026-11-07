import math
import random
import threading
from datetime import datetime, timezone

from .data import generate_cohorts, generate_customers, generate_trend
from .features import FEATURE_KEYS, FEATURE_LABELS, PLAN_ORDER, describe
from .model import load_or_train
from .playbooks import PLAYBOOKS, apply_playbooks, cost_for

LOCK = threading.Lock()

SUCCESS_RATE = {
    "onboarding": 0.62,
    "adoption": 0.55,
    "support": 0.7,
    "payment": 0.8,
    "annual": 0.45,
    "csm": 0.58,
    "reactivation": 0.5,
}

STATE = {
    "customers": None,
    "model": None,
    "risks": None,
    "source": "demo",
    "filename": None,
    "version": 0,
}


def initialize():
    with LOCK:
        if STATE["customers"] is None:
            customers = generate_customers()
            model = load_or_train(customers)
            STATE["customers"] = customers
            STATE["model"] = model
            STATE["risks"] = {customer["id"]: model.score(customer) for customer in customers}
            STATE["version"] = 1


def get_state():
    initialize()
    return STATE


def segment_of(risk):
    if risk >= 0.55:
        return "high"
    if risk >= 0.3:
        return "medium"
    return "low"


def summary(customer, risk):
    return {
        "id": customer["id"],
        "company": customer["company"],
        "industry": customer["industry"],
        "country": customer["country"],
        "plan": customer["plan"],
        "mrr": customer["mrr"],
        "seats": customer["seats"],
        "tenure_months": customer["tenure_months"],
        "risk": round(risk, 4),
        "segment": segment_of(risk),
        "expected_loss": round(customer["mrr"] * risk, 2),
        "trend": customer["usage_trend_30d"],
        "last_login_days": customer["last_login_days"],
    }


def global_drivers(model, customers):
    totals = {key: 0.0 for key in FEATURE_KEYS}
    for customer in customers:
        for key, value in model.contributions(customer):
            totals[key] += abs(value)
    total = sum(totals.values()) or 1.0
    items = [
        {
            "key": key,
            "label": FEATURE_LABELS[key],
            "importance": round(value / total * 100, 1),
        }
        for key, value in totals.items()
    ]
    items.sort(key=lambda item: item["importance"], reverse=True)
    return items[:8]


def best_playbook(customer, model):
    base = model.score(customer)
    best = None
    for playbook in PLAYBOOKS:
        if not playbook["applicable"](customer):
            continue
        updated, changes, cost = apply_playbooks(customer, [playbook["id"]])
        after = model.score(updated)
        saved = max(0.0, base - after) * customer["mrr"]
        expected = saved * SUCCESS_RATE.get(playbook["id"], 0.5)
        if best is None or expected > best["expected_saved"]:
            best = {
                "id": playbook["id"],
                "title": playbook["title"],
                "risk_after": round(after, 4),
                "saved_mrr": round(saved, 2),
                "expected_saved": round(expected, 2),
                "cost": cost,
                "changes": changes,
            }
    return best


def overview():
    state = get_state()
    customers = state["customers"]
    model = state["model"]
    risks = state["risks"]

    total_mrr = sum(customer["mrr"] for customer in customers)
    mrr_at_risk = sum(customer["mrr"] * risks[customer["id"]] for customer in customers)
    average_risk = sum(risks.values()) / len(risks)
    high = sum(1 for value in risks.values() if value >= 0.55)
    medium = sum(1 for value in risks.values() if 0.3 <= value < 0.55)

    potential = 0.0
    for customer in customers:
        risk = risks[customer["id"]]
        if risk < 0.3:
            continue
        best = best_playbook(customer, model)
        if best:
            potential += best["expected_saved"]

    buckets = []
    for index in range(10):
        low = index / 10
        high_edge = (index + 1) / 10
        count = sum(1 for value in risks.values() if low <= value < high_edge or (index == 9 and value >= 0.9))
        buckets.append({"label": f"{index * 10}–{index * 10 + 10}%", "count": count})

    plans = []
    for plan in PLAN_ORDER:
        group = [customer for customer in customers if customer["plan"] == plan]
        if not group:
            continue
        plan_mrr = sum(customer["mrr"] for customer in group)
        plan_risk = sum(risks[customer["id"]] for customer in group) / len(group)
        plans.append(
            {
                "plan": plan,
                "customers": len(group),
                "mrr": round(plan_mrr, 2),
                "risk": round(plan_risk, 4),
                "at_risk": round(sum(customer["mrr"] * risks[customer["id"]] for customer in group), 2),
            }
        )

    ranked = sorted(
        customers,
        key=lambda customer: customer["mrr"] * risks[customer["id"]],
        reverse=True,
    )
    top = [summary(customer, risks[customer["id"]]) for customer in ranked[:8]]

    average_tenure = sum(customer["tenure_months"] for customer in customers) / len(customers)

    return {
        "dataset": {
            "source": state["source"],
            "filename": state["filename"],
            "version": state["version"],
            "customers": len(customers),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "model": {
            **model.metrics,
            "trained_at": model.trained_at,
            "features": len(model.feature_keys),
        },
        "kpis": {
            "customers": len(customers),
            "mrr": round(total_mrr, 2),
            "mrr_at_risk": round(mrr_at_risk, 2),
            "churn_rate": round(average_risk, 4),
            "high_risk": high,
            "medium_risk": medium,
            "potential_saved": round(potential, 2),
            "avg_risk": round(average_risk, 4),
            "avg_tenure": round(average_tenure, 1),
        },
        "risk_distribution": buckets,
        "plans": plans,
        "drivers": global_drivers(model, customers),
        "trend": generate_trend(total_mrr),
        "cohorts": generate_cohorts(),
        "top_customers": top,
    }


def customers_page(segment="all", plan="all", query="", sort="expected_loss", limit=25, offset=0):
    state = get_state()
    customers = state["customers"]
    risks = state["risks"]

    query = (query or "").strip().lower()
    filtered = []
    for customer in customers:
        risk = risks[customer["id"]]
        if segment != "all" and segment_of(risk) != segment:
            continue
        if plan != "all" and customer["plan"] != plan:
            continue
        if query:
            haystack = " ".join(
                [
                    customer["company"],
                    customer["industry"],
                    customer["country"],
                    customer["plan"],
                    str(customer["id"]),
                ]
            ).lower()
            if query not in haystack:
                continue
        filtered.append((customer, risk))

    sorters = {
        "risk": lambda item: item[1],
        "mrr": lambda item: item[0]["mrr"],
        "expected_loss": lambda item: item[0]["mrr"] * item[1],
        "company": lambda item: item[0]["company"].lower(),
        "tenure": lambda item: item[0]["tenure_months"],
    }
    key = sorters.get(sort, sorters["expected_loss"])
    reverse = sort != "company"
    filtered.sort(key=key, reverse=reverse)

    total = len(filtered)
    page = filtered[offset: offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [summary(customer, risk) for customer, risk in page],
    }


def factor_payload(customer, model):
    contributions = model.contributions(customer)
    total = sum(abs(value) for _, value in contributions) or 1.0
    risks = []
    strengths = []
    for key, value in contributions:
        label, text = describe(customer, key)
        item = {
            "key": key,
            "label": label,
            "value": text,
            "impact": round(abs(value), 4),
            "share": round(abs(value) / total * 100, 1),
        }
        if value > 0:
            risks.append(item)
        elif value < 0:
            strengths.append(item)
    risks.sort(key=lambda item: item["impact"], reverse=True)
    strengths.sort(key=lambda item: item["impact"], reverse=True)
    return risks[:5], strengths[:4]


def playbook_payload(customer, model):
    base = model.score(customer)
    items = []
    for playbook in PLAYBOOKS:
        if not playbook["applicable"](customer):
            continue
        updated, changes, cost = apply_playbooks(customer, [playbook["id"]])
        after = model.score(updated)
        saved = max(0.0, base - after) * customer["mrr"]
        expected = saved * SUCCESS_RATE.get(playbook["id"], 0.5)
        annual = expected * 12
        roi = (annual - cost) / cost if cost else None
        items.append(
            {
                "id": playbook["id"],
                "title": playbook["title"],
                "subtitle": playbook["subtitle"],
                "description": playbook["description"],
                "tone": playbook["tone"],
                "cost": cost,
                "success_rate": SUCCESS_RATE.get(playbook["id"], 0.5),
                "risk_before": round(base, 4),
                "risk_after": round(after, 4),
                "saved_mrr": round(saved, 2),
                "expected_saved": round(expected, 2),
                "annual_effect": round(annual, 2),
                "roi": round(roi, 2) if roi is not None else None,
                "changes": changes,
            }
        )
    items.sort(key=lambda item: item["expected_saved"], reverse=True)
    return items


def detail(customer_id):
    state = get_state()
    customer = next((item for item in state["customers"] if item["id"] == customer_id), None)
    if customer is None:
        return None

    model = state["model"]
    risk = state["risks"][customer_id]
    risks, strengths = factor_payload(customer, model)
    playbooks = playbook_payload(customer, model)

    rng = random.Random(customer_id * 7919)
    history = []
    for index in range(8):
        factor = 0.52 + 0.48 * (index / 7) + rng.uniform(-0.05, 0.05)
        value = min(0.99, max(0.02, risk * factor))
        history.append(round(value, 4))
    history[-1] = round(risk, 4)

    return {
        "customer": customer,
        "risk": round(risk, 4),
        "segment": segment_of(risk),
        "expected_loss": round(customer["mrr"] * risk, 2),
        "annual_exposure": round(customer["mrr"] * risk * 12, 2),
        "risks": risks,
        "strengths": strengths,
        "playbooks": playbooks,
        "history": history,
        "health": round((1 - risk) * 100, 1),
    }


def simulate(customer_id, playbook_ids):
    state = get_state()
    customer = next((item for item in state["customers"] if item["id"] == customer_id), None)
    if customer is None:
        return None

    model = state["model"]
    before = model.score(customer)
    updated, changes, cost = apply_playbooks(customer, playbook_ids)
    after = model.score(updated)
    saved = max(0.0, before - after) * customer["mrr"]

    miss = 1.0
    for playbook_id in playbook_ids:
        if playbook_id in SUCCESS_RATE:
            miss *= 1.0 - SUCCESS_RATE[playbook_id]
    success = 1.0 - miss if playbook_ids else 0.0
    expected = saved * success
    annual = expected * 12
    roi = (annual - cost) / cost if cost else None

    return {
        "risk_before": round(before, 4),
        "risk_after": round(after, 4),
        "risk_delta": round(before - after, 4),
        "saved_mrr": round(saved, 2),
        "expected_saved": round(expected, 2),
        "success_rate": round(success, 4),
        "annual_effect": round(annual, 2),
        "cost": cost,
        "roi": round(roi, 2) if roi is not None else None,
        "changes": changes,
        "mrr": customer["mrr"],
    }


def upload(customers, filename):
    state = get_state()
    model = state["model"]
    with LOCK:
        STATE["customers"] = customers
        STATE["risks"] = {customer["id"]: model.score(customer) for customer in customers}
        STATE["source"] = "upload"
        STATE["filename"] = filename
        STATE["version"] += 1
    return len(customers)


def reset():
    with LOCK:
        customers = generate_customers()
        model = STATE["model"]
        STATE["customers"] = customers
        STATE["risks"] = {customer["id"]: model.score(customer) for customer in customers}
        STATE["source"] = "demo"
        STATE["filename"] = None
        STATE["version"] += 1


def sample_rows(limit=40):
    state = get_state()
    return [summary(customer, state["risks"][customer["id"]]) for customer in state["customers"][:limit]]
