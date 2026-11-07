import math

PLAN_ORDER = ["Starter", "Growth", "Scale", "Enterprise"]
PLAN_RANK = {name: index for index, name in enumerate(PLAN_ORDER)}

FEATURE_KEYS = [
    "tenure",
    "active_ratio",
    "adoption",
    "integrations",
    "tickets",
    "nps",
    "payments",
    "trend",
    "last_login",
    "annual",
    "onboarding",
    "csm",
]

FEATURE_LABELS = {
    "tenure": "Стаж",
    "active_ratio": "Активность команды",
    "adoption": "Освоение функций",
    "integrations": "Интеграции",
    "tickets": "Обращения в поддержку",
    "nps": "NPS",
    "payments": "Неудачные платежи",
    "trend": "Динамика использования",
    "last_login": "Последний вход",
    "annual": "Тип контракта",
    "onboarding": "Онбординг",
    "csm": "CSM",
}


def log1p(value):
    return math.log1p(max(0.0, float(value)))


def clamp(value, low, high):
    return max(low, min(high, value))


def vector(customer):
    return [
        log1p(customer["tenure_months"]),
        float(customer["active_ratio"]),
        float(customer["feature_adoption"]),
        float(customer["integrations"]),
        float(customer["support_tickets_30d"]),
        float(customer["nps"]) / 100.0,
        float(customer["payment_failures_12m"]),
        float(customer["usage_trend_30d"]),
        float(customer["last_login_days"]),
        1.0 if customer["contract"] == "annual" else 0.0,
        1.0 if customer["onboarding_completed"] else 0.0,
        1.0 if customer["csm_assigned"] else 0.0,
    ]


def describe(customer, key):
    if key == "tenure":
        return "Стаж", f"{customer['tenure_months']} мес."
    if key == "active_ratio":
        return "Активность команды", f"{customer['active_ratio'] * 100:.0f}% мест активны"
    if key == "adoption":
        return "Освоение функций", f"{customer['feature_adoption'] * 100:.0f}% функций"
    if key == "integrations":
        return "Интеграции", f"{customer['integrations']} подключено"
    if key == "tickets":
        return "Обращения в поддержку", f"{customer['support_tickets_30d']} за 30 дней"
    if key == "nps":
        return "NPS", f"{customer['nps']:+d}"
    if key == "payments":
        return "Неудачные платежи", f"{customer['payment_failures_12m']} за 12 мес."
    if key == "trend":
        return "Динамика использования", f"{customer['usage_trend_30d'] * 100:+.0f}% за 30 дней"
    if key == "last_login":
        return "Последний вход", f"{customer['last_login_days']} дн. назад"
    if key == "annual":
        return "Тип контракта", "годовой" if customer["contract"] == "annual" else "помесячный"
    if key == "onboarding":
        return "Онбординг", "завершён" if customer["onboarding_completed"] else "не завершён"
    if key == "csm":
        return "CSM", "закреплён" if customer["csm_assigned"] else "не закреплён"
    return FEATURE_LABELS.get(key, key), ""
