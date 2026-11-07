import copy


def clamp(value, low, high):
    return max(low, min(high, value))


def _onboarding(customer):
    changes = []
    if not customer["onboarding_completed"]:
        customer["onboarding_completed"] = True
        changes.append("Онбординг завершён")
    if customer["feature_adoption"] < 0.55:
        customer["feature_adoption"] = clamp(customer["feature_adoption"] + 0.14, 0, 0.55)
        changes.append("Освоение функций +14 п.п.")
    customer["usage_trend_30d"] = clamp(customer["usage_trend_30d"] + 0.06, -0.9, 0.9)
    customer["last_login_days"] = min(customer["last_login_days"], 3)
    changes.append("Использование +6 п.п.")
    return changes


def _adoption(customer):
    customer["feature_adoption"] = clamp(customer["feature_adoption"] + 0.15, 0, 1)
    customer["integrations"] = customer["integrations"] + 1
    customer["sessions_30d"] = int(customer["sessions_30d"] * 1.15) + 1
    customer["usage_trend_30d"] = clamp(customer["usage_trend_30d"] + 0.04, -0.9, 0.9)
    return ["Освоение +15 п.п.", "Подключена интеграция", "Сессии +15%"]


def _support(customer):
    changes = []
    if customer["support_tickets_30d"]:
        customer["support_tickets_30d"] = max(0, customer["support_tickets_30d"] - 1)
        changes.append("Закрыта часть обращений")
    if customer["avg_first_response_h"] > 4:
        customer["avg_first_response_h"] = 4.0
        changes.append("Ответ поддержки ускорен")
    if customer["nps"] < 15:
        customer["nps"] = min(100, customer["nps"] + 5)
        changes.append("NPS +5 пунктов")
    return changes or ["Поддержка взята под контроль"]


def _payment(customer):
    customer["payment_failures_12m"] = max(0, customer["payment_failures_12m"] - 1)
    return ["Неудачный платёж устранён"]


def _annual(customer):
    customer["contract"] = "annual"
    customer["discount_pct"] = max(customer["discount_pct"], 15.0)
    return ["Годовой контракт", "Скидка 15%"]


def _csm(customer):
    changes = []
    if not customer["csm_assigned"]:
        customer["csm_assigned"] = True
        changes.append("Закреплён CSM")
    customer["active_ratio"] = clamp(customer["active_ratio"] + 0.07, 0, 0.99)
    customer["usage_trend_30d"] = clamp(customer["usage_trend_30d"] + 0.04, -0.9, 0.9)
    changes.append("Активность +7 п.п.")
    return changes


def _reactivation(customer):
    customer["last_login_days"] = 0
    customer["active_ratio"] = clamp(customer["active_ratio"] + 0.08, 0, 0.99)
    customer["sessions_30d"] = int(customer["sessions_30d"] * 1.2) + 1
    customer["usage_trend_30d"] = clamp(customer["usage_trend_30d"] + 0.08, -0.9, 0.9)
    return ["Клиент вернулся в продукт", "Активность +8 п.п.", "Сессии +20%"]


PLAYBOOKS = [
    {
        "id": "onboarding",
        "title": "Онбординг-спасение",
        "subtitle": "Довести клиента до первой ценности",
        "description": "Персональный онбординг, настройка рабочего пространства и быстрый созвон с командой.",
        "cost": 600,
        "effect": _onboarding,
        "applicable": lambda c: (not c["onboarding_completed"]) or c["feature_adoption"] < 0.45,
        "tone": "violet",
    },
    {
        "id": "adoption",
        "title": "Программа активации",
        "subtitle": "Больше функций — меньше оттока",
        "description": "Кампания по вовлечению: обучение, шаблоны, подключение интеграции и разбор сценариев.",
        "cost": 900,
        "effect": _adoption,
        "applicable": lambda c: c["feature_adoption"] < 0.55 or c["integrations"] <= 1,
        "tone": "cyan",
    },
    {
        "id": "support",
        "title": "Эскалация поддержки",
        "subtitle": "Закрыть боль здесь и сейчас",
        "description": "Старший инженер берёт обращения клиента, ускоряет ответ и фиксирует причину недовольства.",
        "cost": 500,
        "effect": _support,
        "applicable": lambda c: c["support_tickets_30d"] >= 2 or c["avg_first_response_h"] > 6 or c["nps"] < 0,
        "tone": "rose",
    },
    {
        "id": "payment",
        "title": "Восстановление платежа",
        "subtitle": "Убрать финансовый барьер",
        "description": "Ручная сверка, помощь с оплатой и перевод на удобный способ списания.",
        "cost": 150,
        "effect": _payment,
        "applicable": lambda c: c["payment_failures_12m"] >= 1,
        "tone": "amber",
    },
    {
        "id": "annual",
        "title": "Годовой контракт",
        "subtitle": "Зафиксировать клиента надолго",
        "description": "Предложение годового тарифа со скидкой 15% и фиксацией цены.",
        "cost": 0,
        "effect": _annual,
        "applicable": lambda c: c["contract"] == "monthly" and c["mrr"] >= 80,
        "tone": "emerald",
    },
    {
        "id": "csm",
        "title": "Встреча с CSM",
        "subtitle": "Личный контакт решает",
        "description": "Аккаунт-менеджер разбирает цели клиента и собирает план на следующий квартал.",
        "cost": 700,
        "effect": _csm,
        "applicable": lambda c: (not c["csm_assigned"]) or c["mrr"] >= 500,
        "tone": "blue",
    },
    {
        "id": "reactivation",
        "title": "Реактивационная кампания",
        "subtitle": "Вернуть клиента в продукт",
        "description": "Серия писем и звонок с новыми сценариями использования под задачи клиента.",
        "cost": 300,
        "effect": _reactivation,
        "applicable": lambda c: c["last_login_days"] >= 10 or c["usage_trend_30d"] < -0.12,
        "tone": "orange",
    },
]

PLAYBOOK_MAP = {playbook["id"]: playbook for playbook in PLAYBOOKS}


def cost_for(playbook, customer):
    if playbook["id"] == "annual":
        return int(round(customer["mrr"]))
    return int(playbook["cost"])


def apply_playbooks(customer, playbook_ids):
    updated = copy.deepcopy(customer)
    changes = []
    total_cost = 0
    for playbook_id in playbook_ids:
        playbook = PLAYBOOK_MAP.get(playbook_id)
        if not playbook:
            continue
        total_cost += cost_for(playbook, updated)
        for change in playbook["effect"](updated):
            if change not in changes:
                changes.append(change)
    return updated, changes, total_cost
