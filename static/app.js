const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const state = {
  overview: null,
  customers: { items: [], total: 0, limit: 25, offset: 0 },
  filters: { segment: "all", plan: "all", query: "", sort: "expected_loss", offset: 0 },
  view: "overview",
  detail: null,
  selectedPlaybooks: new Set(),
  importOpen: false,
};

const SEGMENT_LABEL = { high: "Высокий", medium: "Средний", low: "Низкий" };
const PLAN_COLORS = {
  Starter: "#22d3ee",
  Growth: "#60a5fa",
  Scale: "#9b7bff",
  Enterprise: "#fbbf24",
};

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function money(value, compact = false) {
  const number = Number(value) || 0;
  if (compact) {
    const absolute = Math.abs(number);
    if (absolute >= 1e6) {
      return "$" + (number / 1e6).toFixed(2).replace(/0+$/, "").replace(/\.$/, "") + "M";
    }
    if (absolute >= 1e3) {
      return "$" + Math.round(number / 1e3) + "K";
    }
    return "$" + Math.round(number);
  }
  return "$" + Math.round(number).toLocaleString("ru-RU").replace(/\u00a0/g, " ");
}

function integer(value) {
  return Math.round(Number(value) || 0).toLocaleString("ru-RU").replace(/\u00a0/g, " ");
}

function plural(count, one, few, many) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function clients(count) {
  const number = Math.round(Number(count) || 0);
  return integer(number) + " " + plural(number, "клиент", "клиента", "клиентов");
}

function percent(value, digits = 1) {
  return ((Number(value) || 0) * 100).toFixed(digits) + "%";
}

function signedPercent(value, digits = 0) {
  const number = (Number(value) || 0) * 100;
  return (number >= 0 ? "+" : "") + number.toFixed(digits) + "%";
}

function riskColor(risk) {
  if (risk >= 0.55) return "#fb7185";
  if (risk >= 0.3) return "#fbbf24";
  return "#34d399";
}

function riskClass(risk) {
  if (risk >= 0.55) return "risk-high";
  if (risk >= 0.3) return "risk-medium";
  return "risk-low";
}

function segmentOf(risk) {
  if (risk >= 0.55) return "high";
  if (risk >= 0.3) return "medium";
  return "low";
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function sparkPath(values, width = 72, height = 26) {
  if (!values || values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - 2 - ((value - min) / span) * (height - 4);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function gaugeSvg(value, size = 170, stroke = 11, id = "g") {
  const radius = (size - stroke * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0.001, Math.min(0.999, value)));
  const color = riskColor(value);
  const center = size / 2;
  return `<svg viewBox="0 0 ${size} ${size}" role="img" aria-label="Риск ${percent(value)}">
    <defs>
      <linearGradient id="gauge-${id}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="${color}" stop-opacity="0.95"/>
        <stop offset="1" stop-color="#22d3ee" stop-opacity="0.9"/>
      </linearGradient>
    </defs>
    <circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="${stroke}"/>
    <circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="url(#gauge-${id})" stroke-width="${stroke}"
      stroke-linecap="round" stroke-dasharray="${circumference.toFixed(2)}"
      stroke-dashoffset="${offset.toFixed(2)}">
      <animate attributeName="stroke-dashoffset" from="${circumference.toFixed(2)}" to="${offset.toFixed(2)}" dur="1s" fill="freeze"/>
    </circle>
  </svg>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = "Ошибка запроса";
    try {
      const payload = await response.json();
      if (payload && payload.detail) message = payload.detail;
    } catch (error) {
      message = response.statusText || message;
    }
    throw new Error(message);
  }
  return response.json();
}

let toastTimer = null;
function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 3200);
}

function animateValue(element, value, format, duration = 750) {
  const start = performance.now();
  function frame(now) {
    const progress = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = format(value * eased);
    if (progress < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function switchView(name) {
  state.view = name;
  $$(".view").forEach((view) => view.classList.add("hidden"));
  const target = $("#view-" + name);
  if (target) target.classList.remove("hidden");
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.viewLink === name));

  const titles = {
    overview: ["Обзор", "Retention intelligence"],
    customers: ["Клиенты", "Все клиенты модели"],
    model: ["Модель", "Прозрачность и метрики"],
  };
  const [title, eyebrow] = titles[name] || titles.overview;
  $("#viewTitle").textContent = title;
  $("#viewEyebrow").textContent = eyebrow;

  if (name === "customers") loadCustomers();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateMeta(overview) {
  const dataset = overview.dataset;
  const kpis = overview.kpis;

  $("#datasetName").textContent = dataset.source === "upload" ? (dataset.filename || "Загруженный CSV") : "Демо-набор";
  $("#datasetMeta").textContent = clients(kpis.customers);
  $("#riskBadge").textContent = integer(kpis.high_risk);
  $("#sidebarAuc").textContent = "AUC " + overview.model.auc.toFixed(2);
  $("#chipAll").textContent = integer(kpis.customers);
  $("#chipHigh").textContent = integer(kpis.high_risk);
  $("#chipMedium").textContent = integer(kpis.medium_risk);
  $("#chipLow").textContent = integer(kpis.customers - kpis.high_risk - kpis.medium_risk);
  $("#resetBtn").classList.toggle("hidden", dataset.source !== "upload");
  $("#importBtn").classList.toggle("hidden", dataset.source === "upload");
}

function renderHero(overview) {
  const kpis = overview.kpis;
  $("#heroCustomers").textContent = integer(kpis.customers);
  $("#heroAuc").textContent = overview.model.auc.toFixed(2);
  $("#heroFeatures").textContent = overview.model.features;
  $("#heroText").textContent = `Под угрозой ${money(kpis.mrr_at_risk, true)} MRR у ${clients(kpis.high_risk + kpis.medium_risk)}. Модель показывает, кто уйдёт, почему и что сделать, чтобы этого не случилось.`;
  const now = new Date();
  $("#updatedAt").textContent = "· обновлён в " + now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  $("#heroGauge").innerHTML = gaugeSvg(kpis.avg_risk, 170, 11, "hero") + `<div class="gauge-center"><b>${percent(kpis.avg_risk)}</b><span>средний риск</span><em>за 30 дней</em></div>`;
}

function renderKpis(overview) {
  const kpis = overview.kpis;
  const cards = [
    {
      label: "MRR под угрозой",
      value: kpis.mrr_at_risk,
      format: (value) => money(value, true),
      sub: `из ${money(kpis.mrr, true)} общего MRR`,
      color: "#fb7185",
      tint: "rgba(251,113,133,.15)",
      icon: '<path d="M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
      spark: [4, 5, 4.6, 6, 5.4, 7, 6.8],
    },
    {
      label: "Ожидаемый отток",
      value: kpis.churn_rate,
      format: (value) => percent(value),
      sub: `≈ ${clients(Math.round(kpis.customers * kpis.churn_rate))} за 30 дней`,
      color: "#fbbf24",
      tint: "rgba(251,191,36,.13)",
      icon: '<path d="M3 17 9 11l4 4 8-8M15 7h6v6"/>',
      spark: [3, 3.4, 3.1, 3.8, 3.5, 4.2, 4],
    },
    {
      label: "Клиенты в зоне риска",
      value: kpis.high_risk,
      format: (value) => integer(value),
      sub: `${integer(kpis.medium_risk)} со средним риском`,
      color: "#9b7bff",
      tint: "rgba(124,92,255,.16)",
      icon: '<path d="M16 20v-1.6c0-2.4-1.9-4.4-4.3-4.4H7.3C4.9 14 3 16 3 18.4V20M9.5 10.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/>',
      spark: [2, 4, 3.4, 5, 4.8, 6, 6.4],
    },
    {
      label: "Потенциал удержания",
      value: kpis.potential_saved,
      format: (value) => money(value, true),
      sub: "с учётом вероятности успеха",
      color: "#34d399",
      tint: "rgba(52,211,153,.13)",
      icon: '<path d="M12 3v18M5 10l7-7 7 7M5 14l7 7 7-7"/>',
      spark: [2, 3, 2.7, 4, 4.4, 5.6, 6.2],
    },
  ];

  $("#kpiGrid").innerHTML = cards
    .map(
      (card, index) => `
      <article class="card kpi" style="--kpi-color:${card.color};--kpi-glow:${card.tint};--kpi-icon-bg:${card.tint}">
        <div class="kpi-head">
          <span class="kpi-label">${card.label}</span>
          <span class="kpi-icon"><svg viewBox="0 0 24 24">${card.icon}</svg></span>
        </div>
        <div class="kpi-value" data-kpi-index="${index}">0</div>
        <div class="kpi-sub">${card.sub}</div>
        <svg class="kpi-spark" viewBox="0 0 72 26"><path d="${sparkPath(card.spark)}"/></svg>
      </article>`
    )
    .join("");

  cards.forEach((card, index) => {
    const element = $(`[data-kpi-index="${index}"]`);
    animateValue(element, card.value, card.format);
  });
}

function renderTrend(points) {
  const container = $("#trendChart");
  const width = 900;
  const height = 268;
  const padding = { left: 52, right: 18, top: 18, bottom: 30 };
  const values = points.map((point) => point.mrr);
  let min = Math.min(...values);
  let max = Math.max(...values);
  const pad = (max - min) * 0.2 || max * 0.1;
  min = Math.max(0, min - pad);
  max = max + pad;

  const x = (index) => padding.left + (index / (points.length - 1)) * (width - padding.left - padding.right);
  const y = (value) => padding.top + (1 - (value - min) / (max - min)) * (height - padding.top - padding.bottom);

  let lastActual = points.length - 1;
  for (let index = 0; index < points.length; index += 1) {
    if (points[index].forecast) {
      lastActual = index - 1;
      break;
    }
  }
  const line = (from, to) =>
    points
      .slice(from, to + 1)
      .map((point, offset) => {
        const index = from + offset;
        return `${index === from ? "M" : "L"}${x(index).toFixed(1)},${y(point.mrr).toFixed(1)}`;
      })
      .join(" ");

  const area = `${line(0, lastActual)} L${x(lastActual).toFixed(1)},${(height - padding.bottom).toFixed(1)} L${x(0).toFixed(1)},${(height - padding.bottom).toFixed(1)} Z`;

  const grid = [0, 0.33, 0.66, 1]
    .map((ratio) => {
      const value = min + (max - min) * ratio;
      const yPos = y(value);
      return `<line x1="${padding.left}" y1="${yPos.toFixed(1)}" x2="${width - padding.right}" y2="${yPos.toFixed(1)}" stroke="rgba(255,255,255,.055)" stroke-width="1"/>
        <text x="${padding.left - 10}" y="${(yPos + 3.5).toFixed(1)}" text-anchor="end" fill="#5f667a" font-size="10">${money(value, true)}</text>`;
    })
    .join("");

  const labels = points
    .map((point, index) =>
      index % 2 === 0 || index === points.length - 1
        ? `<text x="${x(index).toFixed(1)}" y="${height - 8}" text-anchor="middle" fill="#5f667a" font-size="10">${esc(point.month)}</text>`
        : ""
    )
    .join("");

  const dots = points
    .map(
      (point, index) =>
        `<circle cx="${x(index).toFixed(1)}" cy="${y(point.mrr).toFixed(1)}" r="${point.forecast ? 2.6 : 2.2}" fill="${point.forecast ? "#0b0e17" : "#0b0e17"}" stroke="${point.forecast ? "rgba(34,211,238,.7)" : "#9b7bff"}" stroke-width="1.6"/>`
    )
    .join("");

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#7c5cff" stop-opacity=".22"/>
          <stop offset="1" stop-color="#7c5cff" stop-opacity="0"/>
        </linearGradient>
        <linearGradient id="lineStroke" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#9b7bff"/>
          <stop offset="1" stop-color="#22d3ee"/>
        </linearGradient>
      </defs>
      ${grid}
      <path d="${area}" fill="url(#areaFill)"/>
      <path d="${line(0, lastActual)}" fill="none" stroke="url(#lineStroke)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="${line(lastActual, points.length - 1)}" fill="none" stroke="rgba(34,211,238,.65)" stroke-width="2" stroke-dasharray="5 6" stroke-linecap="round"/>
      ${dots}
      ${labels}
      <line id="hoverLine" x1="0" y1="${padding.top}" x2="0" y2="${height - padding.bottom}" stroke="rgba(255,255,255,.22)" stroke-width="1" stroke-dasharray="3 4" opacity="0"/>
      <circle id="hoverDot" cx="0" cy="0" r="4" fill="#0b0e17" stroke="#22d3ee" stroke-width="2" opacity="0"/>
      <rect x="${padding.left}" y="${padding.top}" width="${width - padding.left - padding.right}" height="${height - padding.top - padding.bottom}" fill="transparent" id="hoverArea"/>
    </svg>
    <div class="chart-tooltip" id="chartTooltip"></div>
  `;

  const svg = $("svg", container);
  const hoverLine = $("#hoverLine", container);
  const hoverDot = $("#hoverDot", container);
  const tooltip = $("#chartTooltip", container);
  const hoverArea = $("#hoverArea", container);

  hoverArea.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const chartRect = container.getBoundingClientRect();
    const relative = (event.clientX - rect.left) / rect.width;
    const position = (relative * width - padding.left) / (width - padding.left - padding.right);
    const index = Math.max(0, Math.min(points.length - 1, Math.round(position * (points.length - 1))));
    const point = points[index];

    hoverLine.setAttribute("x1", x(index));
    hoverLine.setAttribute("x2", x(index));
    hoverLine.setAttribute("opacity", "1");
    hoverDot.setAttribute("cx", x(index));
    hoverDot.setAttribute("cy", y(point.mrr));
    hoverDot.setAttribute("opacity", "1");

    tooltip.innerHTML = `<b>${money(point.mrr, true)}</b><span>${esc(point.month)}${point.forecast ? " · прогноз" : ""}</span>`;
    tooltip.style.left = `${event.clientX - chartRect.left}px`;
    tooltip.style.top = `${event.clientY - chartRect.top - 8}px`;
    tooltip.style.opacity = "1";
  });

  hoverArea.addEventListener("mouseleave", () => {
    hoverLine.setAttribute("opacity", "0");
    hoverDot.setAttribute("opacity", "0");
    tooltip.style.opacity = "0";
  });
}

function renderDonut(overview) {
  const kpis = overview.kpis;
  const low = Math.max(0, kpis.customers - kpis.high_risk - kpis.medium_risk);
  const segments = [
    { label: "Низкий", value: low, color: "#34d399" },
    { label: "Средний", value: kpis.medium_risk, color: "#fbbf24" },
    { label: "Высокий", value: kpis.high_risk, color: "#fb7185" },
  ];
  const total = segments.reduce((sum, segment) => sum + segment.value, 0) || 1;
  const size = 160;
  const stroke = 17;
  const radius = (size - stroke) / 2 - 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  const circles = segments
    .map((segment) => {
      const length = (segment.value / total) * circumference;
      const markup = `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="${segment.color}" stroke-width="${stroke}"
        stroke-dasharray="${length.toFixed(2)} ${(circumference - length).toFixed(2)}"
        stroke-dashoffset="${(-offset).toFixed(2)}" stroke-linecap="butt" opacity=".92"/>`;
      offset += length;
      return markup;
    })
    .join("");

  $("#riskDonut").innerHTML = `
    <svg viewBox="0 0 ${size} ${size}">
      <circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="${stroke}"/>
      ${circles}
    </svg>
    <div class="donut-center"><b>${integer(kpis.customers)}</b><span>клиентов</span></div>
  `;

  $("#riskLegend").innerHTML = segments
    .map(
      (segment) => `
      <div class="legend-item">
        <i style="background:${segment.color}"></i>
        ${segment.label}
        <b>${integer(segment.value)}</b>
      </div>`
    )
    .join("");
}

function renderDrivers(overview, target = "#drivers", compact = false) {
  const drivers = overview.drivers.slice(0, compact ? 6 : 7);
  const max = Math.max(...drivers.map((driver) => driver.importance), 1);
  $(target).innerHTML = drivers
    .map(
      (driver) => `
      <div class="driver-row">
        <div class="driver-label">${esc(driver.label)}<span>${driver.importance}%</span></div>
        <div class="driver-track"><div class="driver-fill" style="width:${(driver.importance / max) * 100}%"></div></div>
        <div class="driver-value">${driver.importance}%</div>
      </div>`
    )
    .join("");
}

function renderPlans(overview) {
  const maxMrr = Math.max(...overview.plans.map((plan) => plan.mrr), 1);
  $("#plans").innerHTML = overview.plans
    .map(
      (plan) => `
      <div class="plan-row">
        <div class="plan-name"><i style="background:${PLAN_COLORS[plan.plan] || "#9b7bff"}"></i>${esc(plan.plan)}</div>
        <div class="plan-bar"><span style="width:${(plan.mrr / maxMrr) * 100}%;background:linear-gradient(90deg,${PLAN_COLORS[plan.plan] || "#9b7bff"},rgba(34,211,238,.55))"></span></div>
        <div class="plan-meta"><b>${money(plan.mrr, true)}</b>${clients(plan.customers)} · ${percent(plan.risk)}</div>
      </div>`
    )
    .join("");
}

function riskCell(risk) {
  return `<div class="risk-meter">
    <span class="risk-pill ${riskClass(risk)}"><i></i>${percent(risk)}</span>
    <span class="risk-meter-track"><span style="width:${Math.max(3, risk * 100)}%;background:${riskColor(risk)}"></span></span>
  </div>`;
}

function companyCell(customer) {
  return `<div class="company-cell">
    <span class="avatar">${esc(initials(customer.company))}</span>
    <span><b>${esc(customer.company)}</b><span>${esc(customer.industry)} · ${esc(customer.country)}</span></span>
  </div>`;
}

function trendCell(value) {
  const number = Number(value) || 0;
  const className = number > 0.02 ? "trend-up" : number < -0.02 ? "trend-down" : "trend-flat";
  return `<span class="${className}">${signedPercent(number)}</span>`;
}

function renderTable(target, items, options = {}) {
  const { compact = false } = options;
  if (!items.length) {
    $(target).innerHTML = '<div class="empty">Ничего не найдено. Попробуйте изменить фильтры.</div>';
    return;
  }
  const rows = items
    .map(
      (customer) => `
      <tr data-customer-id="${customer.id}">
        <td>${companyCell(customer)}</td>
        <td><span class="plan-tag">${esc(customer.plan)}</span></td>
        <td class="num">${money(customer.mrr)}</td>
        ${compact ? "" : `<td class="num">${customer.tenure_months} мес.</td>`}
        <td class="num">${trendCell(customer.trend)}</td>
        <td>${riskCell(customer.risk)}</td>
        <td class="num">${money(customer.expected_loss)}</td>
      </tr>`
    )
    .join("");

  $(target).innerHTML = `
    <table class="data">
      <thead>
        <tr>
          <th>Клиент</th>
          <th>Тариф</th>
          <th class="num">MRR</th>
          ${compact ? "" : '<th class="num">Стаж</th>'}
          <th class="num">Тренд</th>
          <th>Риск</th>
          <th class="num">Ожидаемая потеря</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderCohorts(cohorts) {
  const columns = cohorts.columns;
  const rows = cohorts.rows;
  const grid = [];

  grid.push('<div class="cohort-head" style="justify-content:flex-start">Когорта</div>');
  columns.forEach((column) => grid.push(`<div class="cohort-head">${esc(column)}</div>`));

  rows.forEach((row) => {
    grid.push(`<div class="cohort-label"><b>${esc(row.cohort)}</b><span>${integer(row.size)}</span></div>`);
    columns.forEach((column, index) => {
      const value = row.values[index];
      if (value === undefined) {
        grid.push('<div class="cohort-cell" style="background:rgba(255,255,255,.015)"></div>');
        return;
      }
      const alpha = 0.08 + value * 0.62;
      const color = value >= 0.8 ? `rgba(52,211,153,${alpha})` : value >= 0.62 ? `rgba(251,191,36,${alpha})` : `rgba(251,113,133,${alpha})`;
      grid.push(`<div class="cohort-cell" style="background:${color}" title="${esc(row.cohort)} · ${esc(column)}: ${percent(value)}">${Math.round(value * 100)}%</div>`);
    });
  });

  $("#cohorts").innerHTML = `<div class="cohort-grid" style="grid-template-columns:104px repeat(${columns.length}, minmax(52px, 1fr))">${grid.join("")}</div>`;
}

function renderOverview(overview) {
  renderHero(overview);
  renderKpis(overview);
  renderTrend(overview.trend);
  renderDonut(overview);
  renderDrivers(overview);
  renderPlans(overview);
  renderTable("#topTable", overview.top_customers, { compact: true });
  renderCohorts(overview.cohorts);
  renderModel(overview);
}

function renderModel(overview) {
  const model = overview.model;
  $("#modelAucBig").textContent = model.auc.toFixed(2);

  const metrics = [
    { label: "AUC", value: model.auc.toFixed(2), sub: "разделение классов" },
    { label: "Accuracy", value: percent(model.accuracy, 1), sub: "порог " + model.threshold.toFixed(2) },
    { label: "Precision", value: percent(model.precision, 1), sub: "точность тревоги" },
    { label: "Recall", value: percent(model.recall, 1), sub: "поймали оттока" },
    { label: "Brier", value: model.brier.toFixed(3), sub: "калибровка" },
  ];

  $("#modelMetrics").innerHTML = metrics
    .map(
      (metric) => `
      <article class="card kpi">
        <div class="kpi-head">
          <span class="kpi-label">${metric.label}</span>
        </div>
        <div class="kpi-value">${metric.value}</div>
        <div class="kpi-sub">${metric.sub}</div>
      </article>`
    )
    .join("");

  const thresholdLabel = $("#thresholdLabel");
  if (thresholdLabel) thresholdLabel.textContent = model.threshold.toFixed(2);

  const confusion = model.confusion;
  $("#confusion").innerHTML = `
    <div></div>
    <div class="axis">Прогноз: уйдёт</div>
    <div class="axis">Прогноз: останется</div>
    <div class="axis axis-y">Факт: уйдёт</div>
    <div class="confusion-box good"><b>${integer(confusion.true_positive)}</b><span>верно поймали</span></div>
    <div class="confusion-box bad"><b>${integer(confusion.false_negative)}</b><span>пропустили</span></div>
    <div class="axis axis-y">Факт: остаётся</div>
    <div class="confusion-box bad"><b>${integer(confusion.false_positive)}</b><span>ложная тревога</span></div>
    <div class="confusion-box good"><b>${integer(confusion.true_negative)}</b><span>верно</span></div>
  `;

  renderDrivers(overview, "#modelDrivers", true);
}

async function loadCustomers() {
  const { segment, plan, query, sort, offset } = state.filters;
  const params = new URLSearchParams({
    segment,
    plan,
    q: query,
    sort,
    limit: "25",
    offset: String(offset),
  });
  try {
    const data = await api("/api/customers?" + params.toString());
    state.customers = data;
    renderTable("#customersTable", data.items);
    renderPagination(data);
  } catch (error) {
    $("#customersTable").innerHTML = `<div class="empty">${esc(error.message)}</div>`;
  }
}

function renderPagination(data) {
  const from = data.total === 0 ? 0 : data.offset + 1;
  const to = Math.min(data.offset + data.limit, data.total);
  const totalPages = Math.max(1, Math.ceil(data.total / data.limit));
  const page = Math.floor(data.offset / data.limit) + 1;
  $("#pagination").innerHTML = `
    <span>${from}–${to} из ${integer(data.total)}</span>
    <div class="pagination-actions">
      <button class="btn btn-ghost btn-small" data-page="prev" ${data.offset <= 0 ? "disabled" : ""}>← Назад</button>
      <span style="padding:6px 4px">${page} / ${totalPages}</span>
      <button class="btn btn-ghost btn-small" data-page="next" ${to >= data.total ? "disabled" : ""}>Вперёд →</button>
    </div>`;

  $$("[data-page]", $("#pagination")).forEach((button) => {
    button.addEventListener("click", () => {
      const direction = button.dataset.page;
      if (direction === "prev") state.filters.offset = Math.max(0, state.filters.offset - 25);
      else state.filters.offset += 25;
      loadCustomers();
    });
  });
}

function factorRow(factor, tone) {
  return `<div class="factor ${tone}">
    <div class="factor-label"><span>${esc(factor.label)}</span><b>${esc(factor.value)}</b></div>
    <div class="factor-bar"><span style="width:${Math.max(4, Math.min(100, factor.share * 2.4))}%"></span></div>
    <div class="factor-impact">${factor.share}%</div>
  </div>`;
}

function playbookRow(playbook) {
  const selected = state.selectedPlaybooks.has(playbook.id);
  const riskBefore = percent(playbook.risk_before);
  const riskAfter = percent(playbook.risk_after);
  return `<div class="playbook ${selected ? "selected" : ""}" data-playbook="${playbook.id}">
    <div class="playbook-check" role="checkbox" aria-checked="${selected}" tabindex="0"></div>
    <div class="playbook-main">
      <div class="playbook-title">${esc(playbook.title)}</div>
      <div class="playbook-sub">${esc(playbook.subtitle)}</div>
      <div class="playbook-meta">
        <span>риск <b>${riskBefore} → ${riskAfter}</b></span>
        <span>успех <b>${Math.round(playbook.success_rate * 100)}%</b></span>
        <span>стоимость <b>${money(playbook.cost)}</b></span>
      </div>
    </div>
    <div class="playbook-effect">
      <b class="positive">+${money(playbook.expected_saved, true)}</b>
      <span>MRR / мес</span>
    </div>
  </div>`;
}

function renderDetail(payload) {
  const customer = payload.customer;
  $("#drawerTitle").innerHTML = `<h3>${esc(customer.company)}</h3><p>${esc(customer.industry)} · ${esc(customer.country)} · ${esc(customer.plan)} · ${integer(customer.seats)} ${plural(customer.seats, "место", "места", "мест")}</p>`;

  const risks = payload.risks.length
    ? payload.risks.map((factor) => factorRow(factor, "factor-risk")).join("")
    : '<div class="sim-empty">Явных факторов риска не найдено</div>';
  const strengths = payload.strengths.length
    ? payload.strengths.map((factor) => factorRow(factor, "factor-good")).join("")
    : '<div class="sim-empty">Сильных удерживающих факторов нет</div>';

  $("#drawerBody").innerHTML = `
    <div class="detail-top">
      <div class="detail-gauge">
        ${gaugeSvg(payload.risk, 132, 9, "detail")}
        <div class="detail-gauge-caption"><b>${percent(payload.risk)}</b><span>риск оттока</span></div>
      </div>
      <div class="detail-facts">
        <div class="fact"><span>MRR</span><b>${money(customer.mrr)}</b></div>
        <div class="fact"><span>Потеря в месяц</span><b>${money(payload.expected_loss)}</b></div>
        <div class="fact"><span>Стаж</span><b>${customer.tenure_months} мес.</b></div>
        <div class="fact"><span>Последний вход</span><b>${customer.last_login_days} дн. назад</b></div>
        <div class="fact"><span>Сегмент</span><b><span class="risk-pill ${riskClass(payload.risk)}"><i></i>${SEGMENT_LABEL[payload.segment]}</span></b></div>
        <div class="fact"><span>Экспозиция в год</span><b>${money(payload.annual_exposure)}</b></div>
      </div>
    </div>

    <div class="detail-section">
      <div class="detail-section-head"><h4>Динамика риска</h4><span>8 недель</span></div>
      <svg class="sparkline" viewBox="0 0 100 38" preserveAspectRatio="none">
        <path d="${sparkPath(payload.history, 100, 38)}" style="stroke:${riskColor(payload.risk)}"/>
      </svg>
    </div>

    <div class="detail-section">
      <div class="detail-section-head"><h4>Что тянет вниз</h4><span>вклад в риск</span></div>
      <div class="factor-list">${risks}</div>
    </div>

    <div class="detail-section">
      <div class="detail-section-head"><h4>Что удерживает</h4><span>защитные факторы</span></div>
      <div class="factor-list">${strengths}</div>
    </div>

    <div class="detail-section">
      <div class="detail-section-head"><h4>Что сделать</h4><span>выберите сценарии</span></div>
      <div class="playbook-list" id="playbookList">${payload.playbooks.map(playbookRow).join("")}</div>
      <div class="sim-panel">
        <div class="sim-head">
          <h4>Сценарий удержания</h4>
          <button class="btn btn-primary btn-small" id="simulateBtn">Пересчитать</button>
        </div>
        <div id="simResult" class="sim-empty">Выберите одно или несколько действий</div>
      </div>
    </div>
  `;

  $("#playbookList").addEventListener("click", (event) => {
    const card = event.target.closest("[data-playbook]");
    if (!card) return;
    togglePlaybook(card.dataset.playbook, card);
  });

  $("#playbookList").addEventListener("keydown", (event) => {
    if (event.key !== " " && event.key !== "Enter") return;
    const card = event.target.closest("[data-playbook]");
    if (!card) return;
    event.preventDefault();
    togglePlaybook(card.dataset.playbook, card);
  });

  $("#simulateBtn").addEventListener("click", runSimulation);
}

function togglePlaybook(id, card) {
  if (state.selectedPlaybooks.has(id)) state.selectedPlaybooks.delete(id);
  else state.selectedPlaybooks.add(id);
  const selected = state.selectedPlaybooks.has(id);
  card.classList.toggle("selected", selected);
  const check = $(".playbook-check", card);
  if (check) check.setAttribute("aria-checked", String(selected));
}

async function runSimulation() {
  if (!state.detail) return;
  const ids = Array.from(state.selectedPlaybooks);
  const result = $("#simResult");
  if (!ids.length) {
    result.className = "sim-empty";
    result.textContent = "Выберите одно или несколько действий";
    return;
  }

  const button = $("#simulateBtn");
  button.disabled = true;
  button.textContent = "Считаем…";

  try {
    const payload = await api("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id: state.detail.customer.id, playbook_ids: ids }),
    });

    const roi = payload.roi == null ? "—" : payload.roi.toFixed(1) + "×";
    result.className = "";
    result.innerHTML = `
      <div class="sim-result">
        <div class="sim-stat"><span>Риск после</span><b>${percent(payload.risk_after)}</b></div>
        <div class="sim-stat positive"><span>Сохраним в месяц</span><b>${money(payload.expected_saved)}</b></div>
        <div class="sim-stat positive"><span>Эффект в год</span><b>${money(payload.annual_effect)}</b></div>
      </div>
      <div class="sim-changes">${payload.changes.map((change) => `<span>${esc(change)}</span>`).join("")}</div>
      <div class="sim-meta" style="margin-top:8px;color:var(--muted-2);font-size:10.5px">
        Модельный эффект ${money(payload.saved_mrr)} × вероятность успеха ${Math.round(payload.success_rate * 100)}% · стоимость ${money(payload.cost)} · ROI ${roi}
      </div>
    `;
  } catch (error) {
    result.className = "sim-empty";
    result.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Пересчитать";
  }
}

async function openCustomer(id) {
  const backdrop = $("#drawerBackdrop");
  const drawer = $("#drawer");
  backdrop.classList.remove("hidden");
  drawer.classList.remove("hidden");
  requestAnimationFrame(() => {
    backdrop.classList.add("open");
    drawer.classList.add("open");
  });
  document.body.style.overflow = "hidden";

  $("#drawerTitle").innerHTML = '<h3 style="color:var(--muted)">Загрузка…</h3>';
  $("#drawerBody").innerHTML = '<div class="sim-empty" style="padding:30px 0">Считаем профиль клиента…</div>';

  try {
    const payload = await api("/api/customers/" + id);
    state.detail = payload;
    state.selectedPlaybooks = new Set(payload.playbooks.length ? [payload.playbooks[0].id] : []);
    renderDetail(payload);
  } catch (error) {
    $("#drawerBody").innerHTML = `<div class="sim-empty">${esc(error.message)}</div>`;
  }
}

function closeDrawer() {
  const backdrop = $("#drawerBackdrop");
  const drawer = $("#drawer");
  drawer.classList.remove("open");
  backdrop.classList.remove("open");
  document.body.style.overflow = "";
  setTimeout(() => {
    drawer.classList.add("hidden");
    backdrop.classList.add("hidden");
  }, 360);
}

function openImport() {
  state.importOpen = true;
  const modal = $("#importModal");
  modal.classList.remove("hidden");
  requestAnimationFrame(() => modal.classList.add("open"));
  $("#importStatus").textContent = "";
  $("#importStatus").className = "import-status";
}

function closeImport() {
  state.importOpen = false;
  const modal = $("#importModal");
  modal.classList.remove("open");
  setTimeout(() => modal.classList.add("hidden"), 280);
}

async function uploadFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".csv")) {
    showImportStatus("Нужен файл с расширением .csv", "error");
    return;
  }
  showImportStatus("Загружаем и считаем риски…", "");
  const form = new FormData();
  form.append("file", file);

  try {
    const payload = await api("/api/upload", { method: "POST", body: form });
    showImportStatus(`Готово: ${clients(payload.imported)}. Обновляем дашборд…`, "success");
    setTimeout(async () => {
      closeImport();
      await refreshAll();
      toast(`Импортировано ${clients(payload.imported)}`);
    }, 650);
  } catch (error) {
    showImportStatus(error.message, "error");
  }
}

function showImportStatus(message, tone) {
  const element = $("#importStatus");
  element.textContent = message;
  element.className = "import-status" + (tone ? " " + tone : "");
}

async function refreshAll() {
  try {
    const overview = await api("/api/overview");
    state.overview = overview;
    renderOverview(overview);
    updateMeta(overview);
    if (state.view === "customers") await loadCustomers();
    return overview;
  } catch (error) {
    toast("Не удалось загрузить данные: " + error.message);
    throw error;
  }
}

function bindEvents() {
  $$("[data-view-link]").forEach((element) => {
    element.addEventListener("click", (event) => {
      event.preventDefault();
      switchView(element.dataset.viewLink);
    });
  });

  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawerBackdrop").addEventListener("click", closeDrawer);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (state.importOpen) closeImport();
      else if (!$("#drawer").classList.contains("hidden")) closeDrawer();
    }
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      event.preventDefault();
      $("#searchInput").focus();
    }
  });

  $("#searchInput").addEventListener("input", (event) => {
    clearTimeout(window.__searchTimer);
    const value = event.target.value.trim();
    window.__searchTimer = setTimeout(() => {
      state.filters.query = value;
      state.filters.offset = 0;
      if (state.view !== "customers") switchView("customers");
      else loadCustomers();
    }, 260);
  });

  $("#segmentChips").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-segment]");
    if (!chip) return;
    $$(".chip", $("#segmentChips")).forEach((item) => item.classList.toggle("active", item === chip));
    state.filters.segment = chip.dataset.segment;
    state.filters.offset = 0;
    loadCustomers();
  });

  $("#planFilter").addEventListener("change", (event) => {
    state.filters.plan = event.target.value;
    state.filters.offset = 0;
    if (state.view !== "customers") switchView("customers");
    else loadCustomers();
  });

  $("#sortFilter").addEventListener("change", (event) => {
    state.filters.sort = event.target.value;
    state.filters.offset = 0;
    if (state.view !== "customers") switchView("customers");
    else loadCustomers();
  });

  $("#topTable").addEventListener("click", (event) => {
    const row = event.target.closest("[data-customer-id]");
    if (row) openCustomer(Number(row.dataset.customerId));
  });

  $("#customersTable").addEventListener("click", (event) => {
    const row = event.target.closest("[data-customer-id]");
    if (row) openCustomer(Number(row.dataset.customerId));
  });

  $("#runBtn").addEventListener("click", async () => {
    const button = $("#runBtn");
    button.disabled = true;
    const original = button.innerHTML;
    button.textContent = "Считаем…";
    try {
      await refreshAll();
      toast("Прогноз пересчитан");
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  });

  $("#exportBtn").addEventListener("click", () => {
    window.print();
  });

  $("#importBtn").addEventListener("click", openImport);
  $("#importClose").addEventListener("click", closeImport);
  $("#importModal").addEventListener("click", (event) => {
    if (event.target === $("#importModal")) closeImport();
  });

  const dropzone = $("#dropzone");
  const fileInput = $("#fileInput");
  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => uploadFile(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((name) =>
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((name) =>
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove("drag");
    })
  );
  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    uploadFile(file);
  });

  $("#resetBtn").addEventListener("click", async () => {
    try {
      await api("/api/reset", { method: "POST" });
      await refreshAll();
      toast("Демо-данные восстановлены");
    } catch (error) {
      toast(error.message);
    }
  });
}

async function boot() {
  bindEvents();
  try {
    await refreshAll();
  } catch (error) {
    $("#kpiGrid").innerHTML = `<div class="empty">${esc(error.message)}</div>`;
  }
}

boot();
