export const API_BASE_URL = "https://ai11.onrender.com";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error(`接口返回不是 JSON：${response.status}`);
  }

  if (!response.ok) {
    throw new Error(payload?.detail || payload?.error || `请求失败：${response.status}`);
  }

  if (payload && Object.prototype.hasOwnProperty.call(payload, "success")) {
    if (!payload.success) {
      throw new Error(payload.error || "接口返回失败");
    }
    return payload.data;
  }

  return payload;
}

export function searchStock(keyword) {
  return request("/search_stock", {
    method: "POST",
    body: JSON.stringify({ keyword })
  });
}

export function analyzeStock(symbol) {
  return request("/analyze_stock", {
    method: "POST",
    body: JSON.stringify({ symbol })
  });
}

export function screenStocks(limit = 10) {
  return request("/screen_stocks", {
    method: "POST",
    body: JSON.stringify({ limit })
  });
}

export function stockDetail(symbol) {
  return request(`/stock_detail?symbol=${encodeURIComponent(symbol)}`);
}

export function marketOverview() {
  return request("/market_overview", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function intradaySignals() {
  return request("/intraday_signals", {
    method: "POST",
    body: JSON.stringify({ limit: 10 })
  });
}

export function moneyFlowAnomalies() {
  return request("/money_flow_anomalies", {
    method: "POST",
    body: JSON.stringify({ limit: 10 })
  });
}

export function portfolioAnalyze(payload) {
  return request("/portfolio/analyze", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
