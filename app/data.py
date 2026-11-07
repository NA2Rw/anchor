import math
import random

PLAN_SPECS = {
    "Starter": {"weight": 0.42, "mrr": (29, 99), "seats": (1, 12)},
    "Growth": {"weight": 0.32, "mrr": (149, 499), "seats": (8, 60)},
    "Scale": {"weight": 0.18, "mrr": (699, 1990), "seats": (40, 250)},
    "Enterprise": {"weight": 0.08, "mrr": (2400, 12000), "seats": (150, 1400)},
}

INDUSTRIES = [
    "E-commerce",
    "Финтех",
    "Логистика",
    "Медицина",
    "Медиа",
    "Образование",
    "Промышленность",
    "IT и SaaS",
]

COUNTRIES = ["Россия", "Казахстан", "Беларусь", "Германия", "ОАЭ", "Кипр"]

CHANNELS = ["organic", "paid", "referral", "outbound"]

COMPANY_PREFIXES = [
    "Nova", "Aero", "Data", "Fin", "Cloud", "Smart", "Green", "North",
    "Quantum", "Vertex", "Orbit", "Pulse", "Terra", "Lumen", "Atlas",
    "Bright", "Swift", "Silver", "Urban", "Logic", "Meta", "Cyber",
    "Eco", "Prime", "Delta", "Astra", "Vega", "Helio", "Fuse", "Kite",
]

COMPANY_ROOTS = [
    "Retail", "Bank", "Logistics", "Health", "Media", "Soft", "Labs",
    "Works", "Systems", "Digital", "Group", "Tech", "Market", "Cloud",
    "Studio", "Analytics", "Food", "Travel", "Auto", "Realty", "Energy",
]

COMPANY_SUFFIXES = ["", "", "", " Group", " Labs", " Systems", " Digital", " Pro"]

TRUE_WEIGHTS = {
    "intercept": -4.93,
    "active_ratio": 3.15,
    "adoption": 2.25,
    "trend": 3.9,
    "tickets": 0.75,
    "payments": 0.825,
    "last_login": 1.2,
    "onboarding": 0.825,
    "annual": -0.75,
    "csm": -0.525,
    "integrations": -0.12,
    "plan": -0.45,
    "nps": -0.75,
    "tenure": -0.525,
    "response": 0.6,
}


def clamp(value, low, high):
    return max(low, min(high, value))


def pick_plan(rng):
    names = list(PLAN_SPECS)
    weights = [PLAN_SPECS[name]["weight"] for name in names]
    return rng.choices(names, weights=weights, k=1)[0]


def pick_company(rng, used):
    for _ in range(100):
        name = rng.choice(COMPANY_PREFIXES) + rng.choice(COMPANY_ROOTS)
        name += rng.choice(COMPANY_SUFFIXES)
        if name not in used:
            used.add(name)
            return name
    return f"Company {len(used) + 1}"


def log_uniform(rng, low, high):
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def true_probability(customer):
    w = TRUE_WEIGHTS
    z = w["intercept"]
    z += w["active_ratio"] * (1 - customer["active_ratio"])
    z += w["adoption"] * (1 - customer["feature_adoption"])
    z += w["trend"] * max(0.0, -customer["usage_trend_30d"])
    z += w["tickets"] * min(customer["support_tickets_30d"], 4)
    z += w["payments"] * customer["payment_failures_12m"]
    z += w["last_login"] * (1.0 if customer["last_login_days"] > 14 else 0.0)
    z += w["onboarding"] * (0.0 if customer["onboarding_completed"] else 1.0)
    z += w["annual"] * (1.0 if customer["contract"] == "annual" else 0.0)
    z += w["csm"] * (1.0 if customer["csm_assigned"] else 0.0)
    z += w["integrations"] * customer["integrations"]
    z += w["plan"] * (["Starter", "Growth", "Scale", "Enterprise"].index(customer["plan"]) / 3.0)
    z += w["nps"] * (customer["nps"] / 100.0)
    z += w["tenure"] * (math.log1p(customer["tenure_months"]) / 4.0)
    z += w["response"] * (customer["avg_first_response_h"] / 24.0)
    return z


def generate_customers(count=1680, seed=17):
    rng = random.Random(seed)
    label_rng = random.Random(seed + 991)
    customers = []
    used_names = set()

    for index in range(count):
        plan = pick_plan(rng)
        spec = PLAN_SPECS[plan]

        mrr = log_uniform(rng, *spec["mrr"])
        mrr = round(mrr / 10.0) * 10 if mrr >= 200 else round(mrr)
        mrr = float(max(19, mrr))

        seats = int(log_uniform(rng, *spec["seats"]))
        seats = max(1, seats)

        active_ratio = clamp(rng.gauss(0.62, 0.2), 0.02, 0.99)
        adoption = clamp(rng.gauss(0.55, 0.22), 0.01, 0.99)
        tenure = min(60, max(1, int(rng.expovariate(1 / 13.0)) + 1))

        annual_chance = {"Starter": 0.22, "Growth": 0.44, "Scale": 0.62, "Enterprise": 0.78}[plan]
        contract = "annual" if rng.random() < annual_chance else "monthly"

        csm_chance = {"Starter": 0.04, "Growth": 0.28, "Scale": 0.68, "Enterprise": 0.93}[plan]
        csm = rng.random() < csm_chance

        onboarding = rng.random() < 0.82
        if not onboarding:
            adoption = clamp(adoption - rng.uniform(0.05, 0.25), 0.01, 0.99)

        tickets = rng.choices([0, 1, 2, 3, 4, 5], weights=[44, 28, 14, 7, 4, 3], k=1)[0]
        response = clamp(rng.gauss(3.4, 2.1), 0.2, 24.0)
        nps = int(clamp(rng.gauss(26, 42), -100, 100))
        payments = rng.choices([0, 1, 2, 3], weights=[74, 16, 7, 3], k=1)[0]
        trend = clamp(rng.gauss(0.02, 0.18), -0.8, 0.8)
        last_login = rng.choices(
            [0, 1, 2, 3, 5, 7, 10, 14, 21, 30, 45],
            weights=[26, 20, 13, 10, 8, 7, 5, 4, 3, 2, 2],
            k=1,
        )[0]
        integrations = rng.choices([0, 1, 2, 3, 4, 5, 6], weights=[18, 24, 22, 16, 10, 6, 4], k=1)[0]

        sessions = int(max(1, seats * rng.uniform(1.5, 14.0) * max(0.25, active_ratio)))

        discount = 0.0
        if rng.random() < (0.34 if plan in ("Scale", "Enterprise") else 0.18):
            discount = float(rng.choice([5, 10, 15, 20, 25]))

        customer = {
            "id": 1001 + index,
            "company": pick_company(rng, used_names),
            "industry": rng.choice(INDUSTRIES),
            "country": rng.choice(COUNTRIES),
            "plan": plan,
            "mrr": mrr,
            "seats": seats,
            "tenure_months": tenure,
            "active_ratio": round(active_ratio, 3),
            "sessions_30d": sessions,
            "feature_adoption": round(adoption, 3),
            "integrations": integrations,
            "support_tickets_30d": tickets,
            "avg_first_response_h": round(response, 1),
            "nps": nps,
            "payment_failures_12m": payments,
            "discount_pct": discount,
            "contract": contract,
            "onboarding_completed": onboarding,
            "csm_assigned": csm,
            "usage_trend_30d": round(trend, 3),
            "last_login_days": last_login,
            "signup_channel": rng.choices(CHANNELS, weights=[42, 26, 20, 12], k=1)[0],
            "churned": 0,
        }

        latent = true_probability(customer) + label_rng.gauss(0, 0.34)
        probability = 1.0 / (1.0 + math.exp(-latent))
        customer["churned"] = 1 if label_rng.random() < probability else 0

        customers.append(customer)

    return customers


def generate_cohorts(seed=31):
    rng = random.Random(seed)
    labels = ["Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт"]
    columns = ["М0", "М1", "М2", "М3", "М4", "М5", "М6", "М7"]
    rows = []
    for row_index, label in enumerate(labels):
        length = len(labels) - row_index
        size = rng.randint(140, 260)
        values = []
        retained = 1.0
        for month in range(length):
            if month > 0:
                retained *= rng.uniform(0.88, 0.97)
            values.append(round(retained, 4))
        rows.append({"cohort": label, "size": size, "values": values})
    return {"columns": columns, "rows": rows}


def generate_trend(total_mrr, seed=53):
    rng = random.Random(seed)
    months = ["Дек", "Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя"]
    values = []
    value = total_mrr / (1.052 ** (len(months) - 1))
    for index in range(len(months)):
        value *= rng.uniform(1.025, 1.075)
        values.append(value)
    scale = total_mrr / values[-1]
    values = [round(value * scale) for value in values]

    points = [{"month": month, "mrr": values[index], "forecast": False} for index, month in enumerate(months)]
    last = values[-1]
    forecast_months = ["Дек", "Янв", "Фев"]
    forecast_value = last
    for month in forecast_months:
        forecast_value *= rng.uniform(1.03, 1.06)
        points.append({"month": month, "mrr": round(forecast_value), "forecast": True})
    return points
