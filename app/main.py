import csv
import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Anchor", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SimulateRequest(BaseModel):
    customer_id: int
    playbook_ids: list[str] = []


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.svg")
def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg")


@app.get("/api/health")
def health():
    state = analytics.get_state()
    return {
        "status": "ok",
        "model_auc": state["model"].metrics["auc"],
        "customers": len(state["customers"]),
        "source": state["source"],
    }


@app.get("/api/overview")
def overview():
    return analytics.overview()


@app.get("/api/customers")
def customers(
    segment: str = Query("all"),
    plan: str = Query("all"),
    q: str = Query(""),
    sort: str = Query("expected_loss"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return analytics.customers_page(segment, plan, q, sort, limit, offset)


@app.get("/api/customers/{customer_id}")
def customer_detail(customer_id: int):
    payload = analytics.detail(customer_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return payload


@app.post("/api/simulate")
def simulate(request: SimulateRequest):
    payload = analytics.simulate(request.customer_id, request.playbook_ids)
    if payload is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return payload


@app.get("/api/sample.csv")
def sample_csv():
    state = analytics.get_state()
    buffer = io.StringIO()
    columns = [
        "id", "company", "industry", "country", "plan", "mrr", "seats",
        "tenure_months", "active_ratio", "sessions_30d", "feature_adoption",
        "integrations", "support_tickets_30d", "avg_first_response_h", "nps",
        "payment_failures_12m", "discount_pct", "contract",
        "onboarding_completed", "csm_assigned", "usage_trend_30d", "last_login_days",
    ]
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for customer in state["customers"][:120]:
        writer.writerow({column: customer.get(column, "") for column in columns})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="anchor-sample.csv"'},
    )


HEADER_ALIASES = {
    "company": ["company", "name", "customer", "компания", "клиент"],
    "industry": ["industry", "отрасль"],
    "country": ["country", "страна"],
    "plan": ["plan", "тариф", "план"],
    "mrr": ["mrr", "revenue", "monthly_revenue", "выручка", "mrr_usd"],
    "seats": ["seats", "users", "места", "лицензии"],
    "tenure_months": ["tenure", "tenure_months", "months", "стаж"],
    "active_ratio": ["active_ratio", "activity", "активность"],
    "sessions_30d": ["sessions", "sessions_30d", "сессии"],
    "feature_adoption": ["adoption", "feature_adoption", "освоение"],
    "integrations": ["integrations", "интеграции"],
    "support_tickets_30d": ["tickets", "support_tickets", "обращения"],
    "avg_first_response_h": ["response", "first_response_h", "ответ"],
    "nps": ["nps"],
    "payment_failures_12m": ["payment_failures", "failed_payments", "платежи"],
    "discount_pct": ["discount", "discount_pct", "скидка"],
    "contract": ["contract", "контракт"],
    "onboarding_completed": ["onboarding", "onboarding_completed", "онбординг"],
    "csm_assigned": ["csm", "csm_assigned"],
    "usage_trend_30d": ["trend", "usage_trend", "динамика"],
    "last_login_days": ["last_login", "last_login_days", "вход"],
}

PLAN_ALIASES = {
    "starter": "Starter", "старт": "Starter", "start": "Starter",
    "growth": "Growth", "рост": "Growth",
    "scale": "Scale", "масштаб": "Scale", "pro": "Scale",
    "enterprise": "Enterprise", "энтерпрайз": "Enterprise", "корпоративный": "Enterprise",
}

TRUE_VALUES = {"1", "true", "yes", "y", "да", "истина"}


def normalize_header(value):
    return (value or "").strip().lower().replace(" ", "_").replace("-", "_")


def resolve_columns(fieldnames):
    normalized = {normalize_header(name): name for name in fieldnames if name}
    mapping = {}
    for target, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[target] = normalized[alias]
                break
    return mapping


def parse_float(value, default):
    try:
        text = str(value).replace(" ", "").replace(",", ".").replace("$", "").replace("%", "")
        return float(text)
    except (TypeError, ValueError):
        return default


def parse_bool(value, default):
    if value is None:
        return default
    return normalize_header(str(value)) in TRUE_VALUES


def parse_plan(value, mrr):
    if value:
        plan = PLAN_ALIASES.get(normalize_header(str(value)))
        if plan:
            return plan
    if mrr >= 2400:
        return "Enterprise"
    if mrr >= 699:
        return "Scale"
    if mrr >= 149:
        return "Growth"
    return "Starter"


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large")

    text = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(status_code=400, detail="cannot decode file")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="empty csv")

    mapping = resolve_columns(reader.fieldnames)
    if "company" not in mapping or "mrr" not in mapping:
        raise HTTPException(status_code=400, detail="columns company and mrr are required")

    customers = []
    for index, row in enumerate(reader):
        if index >= 20000:
            break
        company = str(row.get(mapping["company"], "")).strip()
        if not company:
            continue
        mrr = max(1.0, parse_float(row.get(mapping["mrr"]), 100.0))
        plan = parse_plan(row.get(mapping.get("plan", "")), mrr)
        seats = max(1, int(parse_float(row.get(mapping.get("seats", "")), 10)))
        customer = {
            "id": 500001 + index,
            "company": company,
            "industry": str(row.get(mapping.get("industry", ""), "IT и SaaS")).strip() or "IT и SaaS",
            "country": str(row.get(mapping.get("country", ""), "Россия")).strip() or "Россия",
            "plan": plan,
            "mrr": round(mrr, 2),
            "seats": seats,
            "tenure_months": max(1, int(parse_float(row.get(mapping.get("tenure_months", "")), 12))),
            "active_ratio": max(0.0, min(1.0, parse_float(row.get(mapping.get("active_ratio", "")), 0.6))),
            "sessions_30d": max(1, int(parse_float(row.get(mapping.get("sessions_30d", "")), seats * 4))),
            "feature_adoption": max(0.0, min(1.0, parse_float(row.get(mapping.get("feature_adoption", "")), 0.55))),
            "integrations": max(0, int(parse_float(row.get(mapping.get("integrations", "")), 2))),
            "support_tickets_30d": max(0, int(parse_float(row.get(mapping.get("support_tickets_30d", "")), 1))),
            "avg_first_response_h": max(0.1, parse_float(row.get(mapping.get("avg_first_response_h", "")), 3.5)),
            "nps": int(max(-100, min(100, parse_float(row.get(mapping.get("nps", "")), 20)))),
            "payment_failures_12m": max(0, int(parse_float(row.get(mapping.get("payment_failures_12m", "")), 0))),
            "discount_pct": max(0.0, min(90.0, parse_float(row.get(mapping.get("discount_pct", "")), 0))),
            "contract": "annual" if normalize_header(str(row.get(mapping.get("contract", ""), ""))) in {"annual", "годовой", "yearly"} else "monthly",
            "onboarding_completed": parse_bool(row.get(mapping.get("onboarding_completed", "")), True),
            "csm_assigned": parse_bool(row.get(mapping.get("csm_assigned", "")), False),
            "usage_trend_30d": max(-1.0, min(1.0, parse_float(row.get(mapping.get("usage_trend_30d", "")), 0.0))),
            "last_login_days": max(0, int(parse_float(row.get(mapping.get("last_login_days", "")), 2))),
            "signup_channel": "upload",
            "churned": 0,
        }
        customers.append(customer)

    if not customers:
        raise HTTPException(status_code=400, detail="no rows found")

    analytics.upload(customers, file.filename or "upload.csv")
    return {"imported": len(customers), "filename": file.filename, "source": "upload"}


@app.post("/api/reset")
def reset():
    analytics.reset()
    return {"status": "ok", "source": "demo"}
