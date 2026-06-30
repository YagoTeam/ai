from __future__ import annotations

import os
import time
from typing import Any

import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, render_template_string, request

from data.provider import DataProviderError, MarketDataProvider, normalize_symbol
from data_completion_engine import get_complete_stock_data
from data_schema import metric_value
from engine_layer import backtest_engine, fund_flow_engine, fundamental_engine, sentiment_engine, strategy_engine, technical_engine
from full_market_scanner import scan_full_market_top10
from intraday_signal_engine import scan_intraday_signals
from market_overview_service import get_market_overview
from money_flow_anomaly_detector import scan_money_flow_anomalies


app = Flask(__name__)
provider = MarketDataProvider()
API_BASE = "http://127.0.0.1:8000"
SCREEN_UNIVERSE = [
    "300394.SZ",
    "600519.SH",
    "300750.SZ",
    "000858.SZ",
    "002594.SZ",
    "600036.SH",
    "000333.SZ",
    "002475.SZ",
    "300308.SZ",
    "688981.SH",
]
SCREEN_CACHE: dict[str, Any] = {"timestamp": 0.0, "rows": []}
SCREEN_CACHE_TTL = 300


HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A股AI量化投资系统 V2-V4</title>
  <style>
    :root { color-scheme: light; --ink: #172033; --muted: #667085; --line: #d8dee8; --bg: #f4f6f8; --panel: #ffffff; --accent: #176b87; --accent-dark: #10546b; --good: #147a45; --bad: #bd3535; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; color: var(--ink); background: var(--bg); }
    header { padding: 22px 28px; background: #0d1b2a; color: white; border-bottom: 4px solid #f0b429; }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    main { max-width: 1120px; margin: 0 auto; padding: 24px; display: grid; gap: 16px; }
    .toolbar, .top-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }
    .search-row { display: grid; grid-template-columns: minmax(220px, 1fr) auto; gap: 10px; align-items: start; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
    label { display: block; font-weight: 650; margin-bottom: 8px; }
    .input-wrap { position: relative; }
    input { width: 100%; height: 42px; border: 1px solid #b8c2cf; border-radius: 6px; padding: 0 12px; font-size: 15px; }
    button { height: 42px; border: 0; border-radius: 6px; padding: 0 18px; background: var(--accent); color: white; cursor: pointer; font-weight: 650; }
    button:hover { background: var(--accent-dark); }
    button:disabled { background: #98a2b3; cursor: not-allowed; }
    .dropdown { position: absolute; z-index: 10; left: 0; right: 0; top: 48px; background: white; border: 1px solid var(--line); border-radius: 6px; max-height: 280px; overflow: auto; box-shadow: 0 10px 24px rgba(16, 24, 40, .12); display: none; }
    .option { width: 100%; display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #eef2f6; }
    .option:hover { background: #f1f6f8; }
    .code { color: var(--muted); font-variant-numeric: tabular-nums; }
    .status { color: var(--muted); min-height: 22px; margin-top: 10px; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .explain-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .metric { border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; background: #fbfcfd; min-height: 76px; }
    .metric span { display: block; color: var(--muted); font-size: 13px; }
    .metric strong { display: block; margin-top: 7px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }
    .explain-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; background: #fbfcfd; }
    .explain-card h3 { margin: 0 0 8px; font-size: 15px; }
    .explain-card p { margin: 6px 0; color: #344054; line-height: 1.55; }
    .final-reason { margin-top: 12px; padding: 12px; border-left: 4px solid var(--accent); background: #f5fbfd; color: #243447; line-height: 1.6; }
    .BUY { color: var(--good); }
    .SELL { color: var(--bad); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { border-bottom: 1px solid #e6ebf1; padding: 9px 8px; text-align: left; }
    th { color: var(--muted); font-weight: 650; }
    .link-btn { height: 32px; padding: 0 12px; font-size: 13px; }
    .detail-panel { display: none; }
    .detail-panel.open { display: block; }
    @media (max-width: 760px) { main { padding: 14px; } .search-row, .cards, .explain-grid { grid-template-columns: 1fr; } button { width: 100%; } }
  </style>
</head>
<body>
  <header><h1>A股AI量化投资系统 V2-V4</h1></header>
  <main>
    <section class="toolbar">
      <label for="keyword">股票代码或名称</label>
      <div class="search-row">
        <div class="input-wrap">
          <input id="keyword" autocomplete="off" placeholder="例如：600519、贵州茅台、宁德时代">
          <div id="dropdown" class="dropdown"></div>
        </div>
        <button id="analyze" disabled>运行分析</button>
      </div>
      <div class="actions">
        <button id="screenBtn">自动选股</button>
        <button id="marketBtn">大盘分析</button>
        <button id="backtestBtn">回测策略</button>
        <button id="intradayBtn">盘中信号</button>
        <button id="anomalyBtn">主力异动</button>
      </div>
      <div id="status" class="status">输入股票代码或名称后选择候选项。</div>
    </section>

    <section class="top-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">大盘概览</h2>
      <div id="marketOverview" class="cards">
        <div class="metric"><span>市场情绪指数</span><strong>-</strong></div>
        <div class="metric"><span>风险偏好</span><strong>-</strong></div>
        <div class="metric"><span>上证/创业板趋势</span><strong>-</strong></div>
        <div class="metric"><span>热门板块</span><strong>-</strong></div>
      </div>
    </section>

    <section class="top-panel">
      <div class="cards">
        <div class="metric"><span>股票</span><strong id="stockName">-</strong></div>
        <div class="metric"><span>现价</span><strong id="price">-</strong></div>
        <div class="metric"><span>综合评分</span><strong id="score">-</strong></div>
        <div class="metric"><span>建议</span><strong id="recommendation">-</strong></div>
      </div>
    </section>

    <section class="top-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">分析解释</h2>
      <div class="explain-grid">
        <div class="explain-card"><h3>技术面</h3><div id="technicalExplain"><p>暂无分析</p></div></div>
        <div class="explain-card"><h3>资金面</h3><div id="fundExplain"><p>暂无分析</p></div></div>
        <div class="explain-card"><h3>基本面</h3><div id="fundamentalExplain"><p>暂无分析</p></div></div>
        <div class="explain-card"><h3>情绪面</h3><div id="sentimentExplain"><p>暂无分析</p></div></div>
      </div>
      <div id="finalReason" class="final-reason">暂无最终理由</div>
    </section>

    <section class="top-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">Top 10 选股</h2>
      <table>
        <thead><tr><th>代码</th><th>名称</th><th>价格</th><th>评分</th><th>建议</th><th>行业</th><th>龙头</th><th>风险</th><th>详情</th></tr></thead>
        <tbody id="top10"><tr><td colspan="9">暂无数据</td></tr></tbody>
      </table>
    </section>

    <section id="detailPanel" class="top-panel detail-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">股票详情</h2>
      <div class="cards">
        <div class="metric"><span>股票</span><strong id="detailName">-</strong></div>
        <div class="metric"><span>现价</span><strong id="detailPrice">-</strong></div>
        <div class="metric"><span>代码</span><strong id="detailSymbol">-</strong></div>
        <div class="metric"><span>详情状态</span><strong id="detailStatus">-</strong></div>
      </div>
      <div class="explain-grid" style="margin-top:12px;">
        <div class="explain-card"><h3>技术面</h3><div id="detailTechnical"><p>暂无分析</p></div></div>
        <div class="explain-card"><h3>资金面</h3><div id="detailFund"><p>暂无分析</p></div></div>
        <div class="explain-card"><h3>基本面</h3><div id="detailFundamental"><p>暂无分析</p></div></div>
        <div class="explain-card"><h3>情绪面</h3><div id="detailSentiment"><p>暂无分析</p></div></div>
      </div>
      <div id="detailFinalReason" class="final-reason">暂无最终理由</div>
    </section>

    <section class="top-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">盘中信号面板</h2>
      <table>
        <thead><tr><th>股票</th><th>信号</th><th>强度</th><th>置信度</th><th>周期</th><th>风险</th><th>触发原因</th><th>详情</th></tr></thead>
        <tbody id="intradaySignals"><tr><td colspan="8">暂无信号</td></tr></tbody>
      </table>
    </section>

    <section class="top-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">主力异动列表</h2>
      <table>
        <thead><tr><th>股票</th><th>异动类型</th><th>强度</th><th>资金变化</th><th>放量</th><th>建议动作</th><th>解读</th><th>详情</th></tr></thead>
        <tbody id="moneyAnomalies"><tr><td colspan="8">暂无异动</td></tr></tbody>
      </table>
    </section>

    <section class="top-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">实时信号</h2>
      <table>
        <thead><tr><th>类型</th><th>级别</th><th>说明</th></tr></thead>
        <tbody id="signals"><tr><td colspan="3">暂无信号</td></tr></tbody>
      </table>
    </section>

    <section class="top-panel">
      <h2 style="margin:0 0 10px;font-size:17px;">回测结果</h2>
      <div class="cards">
        <div class="metric"><span>年化收益</span><strong id="annualReturn">-</strong></div>
        <div class="metric"><span>最大回撤</span><strong id="maxDrawdown">-</strong></div>
        <div class="metric"><span>夏普比率</span><strong id="sharpe">-</strong></div>
        <div class="metric"><span>胜率</span><strong id="winRate">-</strong></div>
      </div>
    </section>
  </main>

  <script>
    const API_BASE = "http://127.0.0.1:8000";
    const input = document.querySelector("#keyword");
    const dropdown = document.querySelector("#dropdown");
    const analyze = document.querySelector("#analyze");
    const screenBtn = document.querySelector("#screenBtn");
    const marketBtn = document.querySelector("#marketBtn");
    const backtestBtn = document.querySelector("#backtestBtn");
    const intradayBtn = document.querySelector("#intradayBtn");
    const anomalyBtn = document.querySelector("#anomalyBtn");
    const statusBox = document.querySelector("#status");
    let selected = null;
    let searchTimer = null;

    function setStatus(text) { statusBox.textContent = text; }
    function fmt(value, digits = 2) { return value === null || value === undefined || Number.isNaN(Number(value)) ? "-" : Number(value).toFixed(digits); }
    function normalizeInputSymbol(value) {
      const raw = value.trim().toUpperCase().replace(/\\s+/g, "");
      const match = raw.match(/(\\d{6})(\\.(SH|SZ))?/);
      if (!match) return null;
      const code = match[1];
      const suffix = match[3] || (code.startsWith("6") ? "SH" : "SZ");
      return `${code}.${suffix}`;
    }
    function enableAnalyzeFromInput() {
      const symbol = normalizeInputSymbol(input.value);
      if (symbol) {
        selected = selected && selected.code === symbol ? selected : { code: symbol, name: "" };
        analyze.disabled = false;
        return true;
      }
      analyze.disabled = true;
      return false;
    }

    input.addEventListener("input", () => {
      selected = null;
      enableAnalyzeFromInput();
      clearTimeout(searchTimer);
      const keyword = input.value.trim();
      if (!keyword) {
        dropdown.style.display = "none";
        setStatus("输入股票代码或名称后选择候选项。");
        return;
      }
      searchTimer = setTimeout(() => searchStocks(keyword), 220);
    });

    async function searchStocks(keyword) {
      setStatus("正在搜索真实A股列表...");
      const res = await fetch(`${API_BASE}/search_stock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword })
      });
      const data = await res.json();
      if (!res.ok) {
        dropdown.style.display = "none";
        setStatus(data.error || "搜索失败");
        return;
      }
      renderDropdown(data);
      if (data.length && normalizeInputSymbol(keyword)) {
        selected = data[0];
        analyze.disabled = false;
        setStatus(`已识别 ${data[0].name || data[0].code}，可直接点击分析。`);
      } else {
        setStatus(data.length ? "请选择一个候选股票。" : "未找到匹配股票。");
      }
    }

    function renderDropdown(items) {
      dropdown.innerHTML = "";
      if (!items.length) {
        dropdown.style.display = "none";
        return;
      }
      items.forEach(item => {
        const row = document.createElement("div");
        row.className = "option";
        row.innerHTML = `<strong>${item.name || item.code}</strong><span class="code">${item.code}</span>`;
        row.addEventListener("click", () => {
          selected = item;
          input.value = `${item.name || ""} ${item.code}`.trim();
          analyze.disabled = false;
          dropdown.style.display = "none";
          setStatus(`已选择 ${item.name || item.code}，点击分析。`);
        });
        dropdown.appendChild(row);
      });
      dropdown.style.display = "block";
    }

    analyze.addEventListener("click", async () => {
      if (!selected && !enableAnalyzeFromInput()) {
        setStatus("请输入 6 位 A股代码或选择候选股票。");
        return;
      }
      analyze.disabled = true;
      setStatus("正在拉取真实行情、资金、基本面与新闻数据...");
      const res = await fetch(`${API_BASE}/analyze_stock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: selected.code })
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(data.error || "分析失败");
        analyze.disabled = false;
        return;
      }
      document.querySelector("#stockName").textContent = `${data.name} ${data.symbol}`;
      document.querySelector("#price").textContent = fmt(data.price);
      document.querySelector("#score").textContent = fmt(data.score, 1);
      const rec = document.querySelector("#recommendation");
      rec.textContent = data.recommendation;
      rec.className = data.recommendation;
      renderExplain(data);
      renderSignals(data.signals || []);
      if (data.top10) renderTop10(data.top10);
      setStatus("分析完成。");
      analyze.disabled = false;
    });

    async function loadTop10() {
      try {
        const res = await fetch(`${API_BASE}/screen_stocks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        const data = await res.json();
        if (res.ok) renderTop10(data.top10 || data || []);
      } catch (err) {
        console.error(err);
      }
    }

    screenBtn.addEventListener("click", async () => {
      screenBtn.disabled = true;
      setStatus("正在进行多因子自动选股...");
      try {
        const res = await fetch(`${API_BASE}/screen_stocks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        const data = await res.json();
        if (!res.ok) {
          setStatus(data.error || "自动选股失败");
          return;
        }
        renderTop10(data.top10 || data || []);
        loadIntradaySignals();
        loadMoneyAnomalies();
        setStatus("自动选股完成。");
      } finally {
        screenBtn.disabled = false;
      }
    });

    intradayBtn.addEventListener("click", async () => {
      intradayBtn.disabled = true;
      setStatus("正在扫描盘中交易信号...");
      try {
        await loadIntradaySignals();
        setStatus("盘中信号扫描完成。");
      } finally {
        intradayBtn.disabled = false;
      }
    });

    anomalyBtn.addEventListener("click", async () => {
      anomalyBtn.disabled = true;
      setStatus("正在检测主力资金异动...");
      try {
        await loadMoneyAnomalies();
        setStatus("主力异动检测完成。");
      } finally {
        anomalyBtn.disabled = false;
      }
    });

    async function loadIntradaySignals() {
      const res = await fetch(`${API_BASE}/intraday_signals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (res.ok) renderIntradaySignals(data.signals || []);
      return data;
    }

    async function loadMoneyAnomalies() {
      const res = await fetch(`${API_BASE}/money_flow_anomalies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (res.ok) renderMoneyAnomalies(data.anomalies || []);
      return data;
    }

    marketBtn.addEventListener("click", async () => {
      marketBtn.disabled = true;
      setStatus("正在获取真实大盘数据...");
      try {
        const res = await fetch(`${API_BASE}/market_overview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        const data = await res.json();
        if (!res.ok) {
          setStatus(data.error || "大盘分析失败");
          return;
        }
        renderMarket(data);
        setStatus("大盘分析完成。");
      } finally {
        marketBtn.disabled = false;
      }
    });

    backtestBtn.addEventListener("click", async () => {
      if (!selected && !enableAnalyzeFromInput()) {
        setStatus("请先输入 6 位 A股代码或选择候选股票。");
        return;
      }
      backtestBtn.disabled = true;
      setStatus("正在使用真实日K运行策略回测...");
      try {
        const res = await fetch(`${API_BASE}/backtest_strategy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol: selected.code, short_window: 5, long_window: 20, days: 180 })
        });
        const data = await res.json();
        if (!res.ok) {
          setStatus(data.error || "回测失败");
          return;
        }
        renderBacktest(data);
        setStatus("回测完成。");
      } finally {
        backtestBtn.disabled = false;
      }
    });

    function renderTop10(rows) {
      const body = document.querySelector("#top10");
      body.innerHTML = "";
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="9">暂无数据</td></tr>';
        return;
      }
      rows.forEach(row => {
        const tr = document.createElement("tr");
        const symbol = row.symbol || row.code;
        const industry = row.sector && row.sector.industry ? row.sector.industry : "-";
        const leader = row.is_leader ? "是" : "否";
        const risk = row.risk_level || "-";
        tr.innerHTML = `<td>${symbol}</td><td>${row.name}</td><td>${fmt(row.price)}</td><td>${fmt(row.score, 1)}</td><td class="${row.recommendation}">${row.recommendation}</td><td>${industry}</td><td>${leader}</td><td>${risk}</td><td><button class="link-btn" data-symbol="${symbol}">查看详情</button></td>`;
        tr.querySelector("button").addEventListener("click", event => {
          event.stopPropagation();
          showStockDetail(symbol);
        });
        body.appendChild(tr);
      });
    }

    async function showStockDetail(symbol) {
      setStatus(`正在加载 ${symbol} 详情...`);
      const panel = document.querySelector("#detailPanel");
      panel.classList.add("open");
      document.querySelector("#detailStatus").textContent = "加载中";
      const res = await fetch(`${API_BASE}/stock_detail?symbol=${encodeURIComponent(symbol)}`);
      const data = await res.json();
      if (!res.ok) {
        document.querySelector("#detailStatus").textContent = "失败";
        setStatus(data.error || "详情加载失败");
        return;
      }
      document.querySelector("#detailName").textContent = data.name || "-";
      document.querySelector("#detailSymbol").textContent = data.symbol || symbol;
      document.querySelector("#detailPrice").textContent = fmt(data.price);
      document.querySelector("#detailStatus").textContent = "已加载";
      renderDetail(data);
      setStatus("详情加载完成。");
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function renderParagraphs(selector, values) {
      const el = document.querySelector(selector);
      el.innerHTML = values.filter(Boolean).map(text => `<p>${text}</p>`).join("");
    }

    function renderExplain(data) {
      const t = data.technical_analysis || {};
      const f = data.fund_flow_analysis || {};
      const b = data.fundamental_analysis || {};
      const s = data.sentiment_analysis || {};
      renderParagraphs("#technicalExplain", [t.ma_trend, t.macd_explanation, t.rsi_explanation, t.volume_explanation, t.trend_judgement]);
      renderParagraphs("#fundExplain", [f.main_fund_direction, f.large_order_direction, f.super_order_direction, f.fund_continuity, f.long_short_balance]);
      renderParagraphs("#fundamentalExplain", [b.pe_view, b.pb_view, b.roe_view, b.revenue_growth_view, b.industry_comparison, b.valuation_summary]);
      renderParagraphs("#sentimentExplain", [s.news_sentiment, s.concept_heat, s.market_impact, s.event_driven]);
      document.querySelector("#finalReason").textContent = data.final_reason || "暂无最终理由";
    }

    function renderDetail(data) {
      const t = data.technical_analysis || {};
      const f = data.fund_flow_analysis || {};
      const b = data.fundamental_analysis || {};
      const s = data.sentiment_analysis || {};
      renderParagraphs("#detailTechnical", [t.ma_trend, t.macd_explanation, t.rsi_explanation, t.volume_explanation, t.trend_judgement]);
      renderParagraphs("#detailFund", [f.main_fund_direction, f.large_order_direction, f.super_order_direction, f.fund_continuity, f.long_short_balance]);
      renderParagraphs("#detailFundamental", [b.pe_view, b.pb_view, b.roe_view, b.revenue_growth_view, b.industry_comparison, b.valuation_summary]);
      renderParagraphs("#detailSentiment", [s.news_sentiment, s.concept_heat, s.market_impact, s.event_driven]);
      document.querySelector("#detailFinalReason").textContent = data.final_reason || "暂无最终理由";
    }

    function renderSignals(rows) {
      const body = document.querySelector("#signals");
      body.innerHTML = "";
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="3">暂无信号</td></tr>';
        return;
      }
      rows.forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.type}</td><td>${row.level}</td><td>${row.message}</td>`;
        body.appendChild(tr);
      });
    }

    function renderIntradaySignals(rows) {
      const body = document.querySelector("#intradaySignals");
      body.innerHTML = "";
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="8">暂无信号</td></tr>';
        return;
      }
      rows.forEach(row => {
        const tr = document.createElement("tr");
        const reasons = (row.trigger_reason || []).join("；");
        tr.innerHTML = `<td>${row.symbol}</td><td>${row.signal_type}</td><td>${fmt(row.signal_strength, 1)}</td><td>${fmt(row.confidence, 2)}</td><td>${row.timeframe}</td><td>${row.risk_level}</td><td>${reasons}</td><td><button class="link-btn" data-symbol="${row.symbol}">查看详情</button></td>`;
        tr.querySelector("button").addEventListener("click", () => showStockDetail(row.symbol));
        body.appendChild(tr);
      });
    }

    function renderMoneyAnomalies(rows) {
      const body = document.querySelector("#moneyAnomalies");
      body.innerHTML = "";
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="8">暂无异动</td></tr>';
        return;
      }
      rows.forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.symbol}</td><td>${row.anomaly_type}</td><td>${row.intensity}</td><td>${fmt(row.money_flow_change, 0)}</td><td>${row.volume_spike ? "是" : "否"}</td><td>${row.action_signal}</td><td>${row.interpretation}</td><td><button class="link-btn" data-symbol="${row.symbol}">查看详情</button></td>`;
        tr.querySelector("button").addEventListener("click", () => showStockDetail(row.symbol));
        body.appendChild(tr);
      });
    }

    function renderMarket(data) {
      const indexes = data.indexes || [];
      const trendText = indexes.map(item => `${item.name}:${item.trend}`).join(" / ") || "-";
      const sectors = ((data.sector_rotation || {}).hot_sectors || []).slice(0, 2).map(item => item.name).join("、") || "-";
      document.querySelector("#marketOverview").innerHTML = `
        <div class="metric"><span>市场情绪指数</span><strong>${fmt(data.market_sentiment_index, 1)}</strong></div>
        <div class="metric"><span>风险偏好</span><strong>${data.risk_preference || "-"}</strong></div>
        <div class="metric"><span>上证/创业板趋势</span><strong>${trendText}</strong></div>
        <div class="metric"><span>热门板块</span><strong>${sectors}</strong></div>`;
    }

    function renderBacktest(data) {
      const m = data.metrics || {};
      document.querySelector("#annualReturn").textContent = m.annual_return === undefined ? "-" : `${(m.annual_return * 100).toFixed(2)}%`;
      document.querySelector("#maxDrawdown").textContent = m.max_drawdown === undefined ? "-" : `${(m.max_drawdown * 100).toFixed(2)}%`;
      document.querySelector("#sharpe").textContent = fmt(m.sharpe, 2);
      document.querySelector("#winRate").textContent = m.win_rate === undefined ? "-" : `${(m.win_rate * 100).toFixed(2)}%`;
    }
    loadTop10();
    loadIntradaySignals();
    loadMoneyAnomalies();
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


@app.route("/search_stock", methods=["OPTIONS"])
@app.route("/analyze_stock", methods=["OPTIONS"])
@app.route("/screen_stocks", methods=["OPTIONS"])
@app.route("/market_overview", methods=["OPTIONS"])
@app.route("/backtest_strategy", methods=["OPTIONS"])
@app.route("/stock_detail", methods=["OPTIONS"])
@app.route("/intraday_signals", methods=["OPTIONS"])
@app.route("/money_flow_anomalies", methods=["OPTIONS"])
def options_response():
    return ("", 204)


@app.post("/search_stock")
def search_stock():
    payload = request.get_json(silent=True) or {}
    keyword = payload.get("keyword") or payload.get("q") or ""
    try:
        return jsonify(provider.search_stock(keyword))
    except (DataProviderError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 502


@app.post("/analyze_stock")
def analyze_stock():
    payload = request.get_json(silent=True) or {}
    try:
        symbol = normalize_symbol(payload.get("symbol", ""))
        result = analyze_one(symbol)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except DataProviderError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        return jsonify({"error": f"analysis failed: {exc}"}), 500


@app.post("/screen_stocks")
def screen_stocks():
    try:
        rows = scan_full_market_top10(limit=10)
        return jsonify(rows)
    except Exception as exc:
        return jsonify({"error": f"screen_stocks failed: {exc}"}), 500


@app.post("/intraday_signals")
def intraday_signals_api():
    try:
        watchlist = scan_full_market_top10(limit=10)
        return jsonify({"signals": scan_intraday_signals(watchlist), "cache_ttl": 60, "watchlist_size": len(watchlist)})
    except Exception as exc:
        return jsonify({"error": f"intraday_signals failed: {exc}", "signals": []}), 500


@app.post("/money_flow_anomalies")
def money_flow_anomalies_api():
    try:
        watchlist = scan_full_market_top10(limit=10)
        return jsonify({"anomalies": scan_money_flow_anomalies(watchlist), "cache_ttl": 60, "watchlist_size": len(watchlist)})
    except Exception as exc:
        return jsonify({"error": f"money_flow_anomalies failed: {exc}", "anomalies": []}), 500


@app.get("/stock_detail")
def stock_detail():
    try:
        symbol = normalize_symbol(request.args.get("symbol", ""))
        result = analyze_one(symbol)
        return jsonify(
            {
                "symbol": result["symbol"],
                "name": result["name"],
                "price": result["price"],
                "technical_analysis": result["technical_analysis"],
                "fund_flow_analysis": result["fund_flow_analysis"],
                "fundamental_analysis": result["fundamental_analysis"],
                "sentiment_analysis": result["sentiment_analysis"],
                "final_reason": result["final_reason"],
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"stock_detail failed: {exc}"}), 502


@app.post("/market_overview")
def market_overview_api():
    try:
        return jsonify(get_market_overview())
    except Exception as exc:
        return jsonify({"error": f"market_overview failed: {exc}"}), 502


@app.post("/backtest_strategy")
def backtest_strategy_api():
    payload = request.get_json(silent=True) or {}
    try:
        symbol = normalize_symbol(payload.get("symbol") or payload.get("code") or "300394")
        short_window = int(payload.get("short_window", 5))
        long_window = int(payload.get("long_window", 20))
        days = int(payload.get("days", 180))
        return jsonify(backtest_engine.run_backtest(symbol, short_window=short_window, long_window=long_window, days=days))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"backtest_strategy failed: {exc}"}), 502


def analyze_one(symbol: str) -> dict[str, Any]:
    full_data = get_complete_stock_data(symbol)
    quote = full_data["price_data"]
    technical = full_data["technical_data"]
    funds = full_data["fund_flow_data"]
    fundamental = full_data["fundamental_data"]
    sentiment = full_data["sentiment_data"]
    warnings = [
        data.get("message")
        for data in [quote, technical, funds, fundamental, sentiment]
        if data.get("status") not in {"OK"} and data.get("message")
    ]
    if quote.get("status") == "NO_DATA":
        raise DataProviderError(quote.get("message", "price unavailable"))
    if technical.get("status") == "NO_DATA":
        raise DataProviderError(technical.get("message", "technical data unavailable"))
    technical_score = technical_engine.score(technical)
    fund_score = fund_flow_engine.score(funds)
    fundamental_score = fundamental_engine.score(fundamental)
    sentiment_score = sentiment_engine.score(sentiment)
    total_score = strategy_engine.weighted_score(
        [
            (technical_score, strategy_engine.WEIGHTS["technical"]),
            (fund_score, strategy_engine.WEIGHTS["fund_flow"]),
            (fundamental_score, strategy_engine.WEIGHTS["fundamental"]),
            (sentiment_score, strategy_engine.WEIGHTS["sentiment"]),
        ]
    )
    recommendation = strategy_engine.recommendation(total_score)
    explain = build_explain_layer(
        technical=technical,
        funds=funds,
        fundamental=fundamental,
        sentiment=sentiment,
        technical_score=technical_score,
        fund_score=fund_score,
        fundamental_score=fundamental_score,
        sentiment_score=sentiment_score,
        total_score=total_score,
        recommendation=recommendation,
    )
    result = {
        "symbol": symbol,
        "code": symbol,
        "name": quote["name"],
        "price": metric_value(quote["price"]),
        "change_pct": metric_value(quote["change_pct"]),
        "volume": metric_value(quote["volume"]),
        "price_data": quote,
        "technical": technical | {"score": technical_score},
        "technical_data": wrap_trusted_value(technical | {"score": technical_score}, "REAL" if technical.get("data_source") == "REAL" else "ESTIMATED"),
        "fundamental": fundamental | {"score": fundamental_score},
        "fundamental_data": wrap_trusted_value(fundamental | {"score": fundamental_score}, fundamental.get("data_source", "ESTIMATED")),
        "sentiment": sentiment | {"score": sentiment_score},
        "sentiment_data": wrap_trusted_value(sentiment | {"score": sentiment_score}, sentiment.get("data_source", "AI_INFERRED")),
        "funds": funds | {"score": fund_score},
        "fund_flow_data": wrap_trusted_value(funds | {"score": fund_score}, funds.get("data_source", "ESTIMATED")),
        "score": total_score,
        "recommendation": recommendation,
        "factor_scores": {
            "technical": technical_score,
            "fund_flow": fund_score,
            "fundamental": fundamental_score,
            "sentiment": sentiment_score,
            "weights": strategy_engine.WEIGHTS,
        },
        "data_status": full_data.get("data_status", "PARTIAL"),
        "technical_analysis": explain["technical_analysis"],
        "fund_flow_analysis": explain["fund_flow_analysis"],
        "fundamental_analysis": explain["fundamental_analysis"],
        "sentiment_analysis": explain["sentiment_analysis"],
        "final_reason": explain["final_reason"],
        "warnings": warnings,
        "data_source": build_data_trust_summary(full_data),
        "raw_data": full_data,
    }
    result["signals"] = strategy_engine.realtime_signals(result)
    result["reasons"] = strategy_engine.stock_reasons(
        {
            "technical_data": technical,
            "fund_flow_data": funds,
            "fundamental_data": fundamental,
            "sentiment_data": sentiment,
        }
    )
    return result


def wrap_trusted_value(value: dict[str, Any], data_source: str) -> dict[str, Any]:
    wrapped = dict(value)
    wrapped["value"] = dict(value)
    wrapped["data_source"] = data_source
    return wrapped


def build_top10(seed_symbol: str | None = None) -> list[dict[str, Any]]:
    if not seed_symbol and SCREEN_CACHE["rows"] and time.time() - float(SCREEN_CACHE["timestamp"]) < SCREEN_CACHE_TTL:
        return list(SCREEN_CACHE["rows"])
    rows: list[dict[str, Any]] = []
    symbols = build_screen_universe(limit=12)
    if seed_symbol:
        symbols = [seed_symbol] + [code for code in symbols if code != seed_symbol]
    for symbol in symbols:
        try:
            result = analyze_one(symbol)
            rows.append(
                {
                    "symbol": result["symbol"],
                    "name": result["name"],
                    "price": result["price"],
                    "score": result["score"],
                    "recommendation": "BUY",
                    "sector": stock_sector(result),
                }
            )
        except Exception:
            continue
    top_rows = sorted(rows, key=lambda row: row["score"] if row["score"] is not None else -1, reverse=True)[:10]
    if not seed_symbol:
        SCREEN_CACHE["timestamp"] = time.time()
        SCREEN_CACHE["rows"] = list(top_rows)
    return top_rows


def build_screen_universe(limit: int = 30) -> list[str]:
    symbols = eastmoney_screen_universe(limit=limit)
    if symbols:
        return symbols
    return list(SCREEN_UNIVERSE)[:limit]


def eastmoney_screen_universe(limit: int = 80) -> list[str]:
    page_size = min(max(limit, 20), 100)
    params = {
        "pn": 1,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f6",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f2,f3,f5,f6",
    }
    try:
        response = requests.get("https://push2.eastmoney.com/api/qt/clist/get", params=params, timeout=provider.timeout)
        response.raise_for_status()
        rows = (response.json().get("data") or {}).get("diff") or []
    except Exception:
        return []
    symbols: list[str] = []
    for row in rows:
        code = str(row.get("f12") or "").strip()
        if len(code) == 6 and code.isdigit():
            symbols.append(normalize_symbol(code))
    return symbols[:limit]


def stock_sector(result: dict[str, Any]) -> dict[str, str]:
    fundamental = result.get("fundamental_data") or {}
    sector = fundamental.get("sector") or ""
    return {"industry": str(sector), "sub_industry": ""}


def calculate_technical(bars: pd.DataFrame) -> dict[str, float | str | None]:
    frame = bars.copy().sort_values("date")
    close = frame["close"]
    frame["ma5"] = close.rolling(5).mean()
    frame["ma20"] = close.rolling(20).mean()
    frame["ma60"] = close.rolling(60).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    frame["macd_dif"] = ema12 - ema26
    frame["macd_dea"] = frame["macd_dif"].ewm(span=9, adjust=False).mean()
    frame["macd"] = (frame["macd_dif"] - frame["macd_dea"]) * 2
    frame["rsi"] = rsi(close)
    frame["volume_change"] = frame["volume"] / frame["volume"].rolling(20).mean() - 1
    latest = frame.tail(1).iloc[0]
    trend = "UP" if latest["ma5"] > latest["ma20"] > latest["ma60"] and latest["macd"] > 0 else "DOWN" if latest["ma5"] < latest["ma20"] < latest["ma60"] and latest["macd"] < 0 else "SIDEWAYS"
    return {
        "ma5": _num(latest["ma5"]),
        "ma20": _num(latest["ma20"]),
        "ma60": _num(latest["ma60"]),
        "macd": {"dif": _num(latest["macd_dif"]), "dea": _num(latest["macd_dea"]), "hist": _num(latest["macd"])},
        "rsi": _num(latest["rsi"]),
        "volume_change": _num(latest["volume_change"]),
        "trend": trend,
    }


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def score_technical(technical: dict[str, Any]) -> float | None:
    if technical.get("status") == "NO_DATA":
        return None
    score = 50.0
    trend = metric_value(technical.get("trend"))
    score += 18 if trend == "UP" else -15 if trend == "DOWN" else 0
    rsi_value = _num(technical.get("rsi"))
    if rsi_value is not None:
        score += float(np.clip((rsi_value - 50) * 0.35, -12, 12))
    volume_change = _num(technical.get("volume_change"))
    if volume_change is not None:
        score += float(np.clip(volume_change * 20, -10, 12))
    macd_hist = _num(technical.get("macd", {}).get("hist"))
    if macd_hist is not None:
        score += 6 if macd_hist > 0 else -6
    return round(float(np.clip(score, 0, 100)), 2)


def score_funds(funds: dict[str, float | None]) -> float | None:
    if funds.get("status") not in {"OK", "COMPLETED"}:
        return None
    score = 50.0
    for key, weight in [("main_flow", 18), ("super_order", 10), ("large_order", 8)]:
        value = _num(funds.get(key))
        if value is None:
            continue
        score += weight if value > 0 else -weight if value < 0 else 0
    return round(float(np.clip(score, 0, 100)), 2)


def score_fundamental(fundamental: dict[str, float | None]) -> float | None:
    if fundamental.get("status") not in {"OK", "COMPLETED"}:
        return None
    score = 50.0
    estimated = fundamental.get("estimated") or {}
    pe = _num(fundamental.get("pe")) if _num(fundamental.get("pe")) is not None else _num(estimated.get("pe"))
    pb = _num(fundamental.get("pb")) if _num(fundamental.get("pb")) is not None else _num(estimated.get("pb"))
    roe = _percent_to_ratio(_num(fundamental.get("roe")) if _num(fundamental.get("roe")) is not None else _num(estimated.get("roe")))
    growth = _percent_to_ratio(_num(fundamental.get("revenue_growth")) if _num(fundamental.get("revenue_growth")) is not None else _num(estimated.get("revenue_growth")))
    if pe is not None:
        score += 12 if 0 < pe <= 35 else -8 if pe > 80 or pe <= 0 else 2
    if pb is not None:
        score += 8 if 0 < pb <= 4 else -6 if pb > 8 or pb <= 0 else 1
    if roe is not None:
        score += float(np.clip(roe * 120, -12, 18))
    if growth is not None:
        score += float(np.clip(growth * 80, -10, 16))
    return round(float(np.clip(score, 0, 100)), 2)


def build_data_trust_summary(full_data: dict[str, Any]) -> dict[str, str]:
    price_data = full_data.get("price_data", {})
    technical_data = full_data.get("technical_data", {})
    fund_flow_data = full_data.get("fund_flow_data", {})
    fundamental_data = full_data.get("fundamental_data", {})
    sentiment_data = full_data.get("sentiment_data", {})
    return {
        "price": price_data.get("data_source", "REAL" if price_data.get("status") == "OK" else "ESTIMATED"),
        "kline": "REAL" if technical_data.get("data_source") == "REAL" else "ESTIMATED",
        "technical": "REAL" if technical_data.get("data_source") == "REAL" else "ESTIMATED",
        "fund_flow": fund_flow_data.get("data_source", "ESTIMATED"),
        "fundamental": fundamental_data.get("data_source", "ESTIMATED"),
        "sentiment": sentiment_data.get("data_source", "AI_INFERRED"),
    }


def score_sentiment(sentiment: dict[str, Any]) -> float | None:
    if sentiment.get("status") not in {"OK", "COMPLETED"}:
        return None
    label = metric_value(sentiment.get("sentiment")) or "NEUTRAL"
    confidence = float(metric_value(sentiment.get("confidence")) or 0)
    if label == "POSITIVE":
        return round(float(np.clip(50 + confidence * 35, 0, 100)), 2)
    if label == "NEGATIVE":
        return round(float(np.clip(50 - confidence * 35, 0, 100)), 2)
    return round(50.0, 2)


def weighted_score(parts: list[tuple[float | None, float]]) -> float:
    valid = [(score, weight) for score, weight in parts if score is not None]
    if not valid:
        raise DataProviderError("no scored module is available")
    total_weight = sum(weight for _, weight in valid)
    return round(sum(float(score) * weight for score, weight in valid) / total_weight, 2)


def build_explain_layer(
    technical: dict[str, Any],
    funds: dict[str, float | None],
    fundamental: dict[str, float | None],
    sentiment: dict[str, Any],
    technical_score: float | None,
    fund_score: float | None,
    fundamental_score: float | None,
    sentiment_score: float | None,
    total_score: float,
    recommendation: str,
) -> dict[str, Any]:
    technical_analysis = explain_technical(technical, technical_score)
    fund_flow_analysis = explain_fund_flow(funds, fund_score)
    fundamental_analysis = explain_fundamental(fundamental, fundamental_score)
    sentiment_analysis = explain_sentiment(sentiment, sentiment_score)
    final_reason = (
        f"综合评分 {total_score:.2f}，对应建议为 {recommendation}。"
        f"评分按可用模块归一化计算，原始权重为技术面30%、资金面30%、基本面20%、情绪面20%："
        f"技术面 {_score_text(technical_score)}，资金面 {_score_text(fund_score)}，"
        f"基本面 {_score_text(fundamental_score)}，情绪面 {_score_text(sentiment_score)}。"
        f"当前结论主要受{technical_analysis['trend_judgement']}、"
        f"{fund_flow_analysis['long_short_balance']}、"
        f"{fundamental_analysis['valuation_summary']}和"
        f"{sentiment_analysis['market_impact']}共同影响。"
    )
    return {
        "technical_analysis": technical_analysis,
        "fund_flow_analysis": fund_flow_analysis,
        "fundamental_analysis": fundamental_analysis,
        "sentiment_analysis": sentiment_analysis,
        "final_reason": final_reason,
    }


def explain_technical(technical: dict[str, Any], score: float | None) -> dict[str, Any]:
    ma5 = _num(technical.get("ma5"))
    ma20 = _num(technical.get("ma20"))
    ma60 = _num(technical.get("ma60"))
    macd = technical.get("macd", {}) or {}
    macd_hist = _num(macd.get("hist"))
    rsi_value = _num(technical.get("rsi"))
    volume_change = _num(technical.get("volume_change"))
    trend = metric_value(technical.get("trend"))

    if ma5 is not None and ma20 is not None and ma60 is not None:
        if ma5 > ma20 > ma60:
            ma_text = f"MA5({ma5:.2f}) > MA20({ma20:.2f}) > MA60({ma60:.2f})，短中长期均线呈多头排列。"
        elif ma5 < ma20 < ma60:
            ma_text = f"MA5({ma5:.2f}) < MA20({ma20:.2f}) < MA60({ma60:.2f})，均线呈空头排列。"
        else:
            ma_text = f"MA5({ma5:.2f})、MA20({ma20:.2f})、MA60({ma60:.2f}) 相互交错，趋势仍在整理。"
    else:
        ma_text = "均线数据不足，暂按趋势不明确处理。"

    if macd_hist is None:
        macd_state = "震荡"
        macd_text = "MACD数据不足，暂按震荡处理。"
    elif macd_hist > 0:
        macd_state = "金叉/偏多"
        macd_text = f"MACD柱值为 {macd_hist:.2f}，DIF高于DEA的动能偏正，属于金叉或偏多状态。"
    elif macd_hist < 0:
        macd_state = "死叉/偏空"
        macd_text = f"MACD柱值为 {macd_hist:.2f}，DIF低于DEA的动能偏负，属于死叉或偏空状态。"
    else:
        macd_state = "震荡"
        macd_text = "MACD柱值接近0，多空动能暂时均衡。"

    if rsi_value is None:
        rsi_state = "正常"
        rsi_text = "RSI数据不足，暂按正常区间处理。"
    elif rsi_value >= 70:
        rsi_state = "超买"
        rsi_text = f"RSI为 {rsi_value:.2f}，处于超买区，短线追高风险上升。"
    elif rsi_value <= 30:
        rsi_state = "超卖"
        rsi_text = f"RSI为 {rsi_value:.2f}，接近或处于超卖区，需观察是否出现企稳反弹。"
    else:
        rsi_state = "正常"
        rsi_text = f"RSI为 {rsi_value:.2f}，位于正常区间，情绪未明显过热或过冷。"

    if volume_change is None:
        volume_text = "成交量变化数据不足，量能按中性处理。"
    elif volume_change > 0.2:
        volume_text = f"成交量较20日均量放大 {volume_change:.2%}，交易活跃度明显提升。"
    elif volume_change < -0.2:
        volume_text = f"成交量较20日均量萎缩 {abs(volume_change):.2%}，资金参与度下降。"
    else:
        volume_text = f"成交量较20日均量变化 {volume_change:.2%}，量能整体平稳。"

    trend_text = {"UP": "上涨", "DOWN": "下跌", "SIDEWAYS": "震荡"}.get(str(trend), "震荡")
    return {
        "score": score,
        "status": technical.get("status", "OK"),
        "source": technical.get("source", ""),
        "data_source": technical.get("data_source", "REAL" if technical.get("status") == "OK" else "ESTIMATED"),
        "ma_trend": ma_text,
        "macd_status": macd_state,
        "macd_explanation": macd_text,
        "rsi_status": rsi_state,
        "rsi_explanation": rsi_text,
        "volume_explanation": volume_text,
        "trend_judgement": f"当前趋势判断为{trend_text}，技术面{_score_sentence(score)}。",
    }


def explain_fund_flow(funds: dict[str, float | None], score: float | None) -> dict[str, Any]:
    main_flow = _num(funds.get("main_flow"))
    large_order = _num(funds.get("large_order"))
    super_order = _num(funds.get("super_order"))

    if main_flow is None:
        main_text = "主力资金接口未返回有效数值，资金面按中性处理。"
    elif main_flow > 0:
        main_text = f"主力资金归一化净流入 {main_flow:.2%}，说明主动买盘占优。"
    elif main_flow < 0:
        main_text = f"主力资金归一化净流出 {abs(main_flow):.2%}，说明主动卖盘压力较大。"
    else:
        main_text = "主力资金净流入接近0，多空资金暂时均衡。"

    def order_text(label: str, value: float | None) -> str:
        if value is None:
            return f"{label}数据未返回，暂不形成方向性判断。"
        if value > 0:
            return f"{label}归一化净流入 {value:.2%}，偏向多头。"
        if value < 0:
            return f"{label}归一化净流出 {abs(value):.2%}，偏向空头。"
        return f"{label}净额接近0，方向中性。"

    known_values = [value for value in [main_flow, large_order, super_order] if value is not None]
    positive_count = sum(value > 0 for value in known_values)
    negative_count = sum(value < 0 for value in known_values)
    if not known_values:
        continuity = "资金持续性无法确认：当前资金流接口未提供主力、大单、超大单有效数据。"
        balance = "多空力量对比无法确认：缺少资金流方向数据，资金面不参与评分。"
    elif positive_count > negative_count:
        continuity = "资金持续性偏正：主力/大单/超大单中流入项更多。"
        balance = "多空力量对比偏多：买方资金力量强于卖方。"
    elif negative_count > positive_count:
        continuity = "资金持续性偏弱：主力/大单/超大单中流出项更多。"
        balance = "多空力量对比偏空：卖方资金力量强于买方。"
    else:
        continuity = "资金持续性一般：流入与流出信号相互抵消。"
        balance = "多空力量对比均衡：尚未形成明显方向。"

    return {
        "score": score,
        "status": funds.get("status", "NO_DATA"),
        "source": funds.get("source", ""),
        "data_source": funds.get("data_source", "ESTIMATED"),
        "message": funds.get("message", ""),
        "main_fund_direction": main_text,
        "large_order_direction": order_text("大单", large_order),
        "super_order_direction": order_text("超大单", super_order),
        "fund_continuity": continuity,
        "long_short_balance": f"{balance} 资金面{_score_sentence(score)}。",
    }


def explain_fundamental(fundamental: dict[str, float | None], score: float | None) -> dict[str, Any]:
    estimated = fundamental.get("estimated") or {}
    pe = _num(fundamental.get("pe"))
    pb = _num(fundamental.get("pb"))
    roe = _num(fundamental.get("roe"))
    growth = _num(fundamental.get("revenue_growth"))
    pe_for_view = pe if pe is not None else _num(estimated.get("pe"))
    pb_for_view = pb if pb is not None else _num(estimated.get("pb"))
    roe_for_view = roe if roe is not None else _num(estimated.get("roe"))
    growth_for_view = growth if growth is not None else _num(estimated.get("revenue_growth"))

    pe_prefix = "真实PE" if pe is not None else "真实PE缺失，估算PE"
    if pe_for_view is None:
        pe_text = "PE数据未返回，且无估算值，无法判断市盈率高估或低估。"
    elif pe_for_view <= 0:
        pe_text = f"{pe_prefix}为 {pe_for_view:.2f}，可能受亏损或异常口径影响，估值参考意义较弱。"
    elif pe_for_view <= 20:
        pe_text = f"{pe_prefix}为 {pe_for_view:.2f}，相对偏低，估值压力较小。"
    elif pe_for_view <= 50:
        pe_text = f"{pe_prefix}为 {pe_for_view:.2f}，处于中等偏高区间，需要结合成长性验证。"
    else:
        pe_text = f"{pe_prefix}为 {pe_for_view:.2f}，估值偏高，对业绩兑现要求较高。"

    pb_prefix = "真实PB" if pb is not None else "真实PB缺失，估算PB"
    if pb_for_view is None:
        pb_text = "PB数据未返回，且无估算值，无法判断净资产估值。"
    elif pb_for_view <= 1:
        pb_text = f"{pb_prefix}为 {pb_for_view:.2f}，接近破净或低净资产估值。"
    elif pb_for_view <= 4:
        pb_text = f"{pb_prefix}为 {pb_for_view:.2f}，净资产估值相对合理。"
    elif pb_for_view <= 10:
        pb_text = f"{pb_prefix}为 {pb_for_view:.2f}，净资产估值偏高。"
    else:
        pb_text = f"{pb_prefix}为 {pb_for_view:.2f}，净资产估值显著偏高。"

    roe_ratio = _percent_to_ratio(roe_for_view)
    roe_prefix = "真实ROE" if roe is not None else "真实ROE缺失，估算ROE"
    if roe_ratio is None:
        roe_text = "ROE数据未返回，且无估算值，盈利质量暂按中性处理。"
    elif roe_ratio >= 0.15:
        roe_text = f"{roe_prefix}为 {roe_for_view:.2f}，盈利能力较强。"
    elif roe_ratio >= 0.08:
        roe_text = f"{roe_prefix}为 {roe_for_view:.2f}，盈利能力处于正常水平。"
    elif roe_ratio >= 0:
        roe_text = f"{roe_prefix}为 {roe_for_view:.2f}，盈利能力偏弱。"
    else:
        roe_text = f"{roe_prefix}为 {roe_for_view:.2f}，盈利能力承压。"

    growth_ratio = _percent_to_ratio(growth_for_view)
    growth_prefix = "真实营收增长" if growth is not None else "真实营收增长缺失，估算营收增长"
    if growth_ratio is None:
        growth_text = "营收增长数据未返回，且无估算值，成长趋势暂无法确认。"
    elif growth_ratio >= 0.2:
        growth_text = f"{growth_prefix}为 {growth_for_view:.2f}，成长趋势较强。"
    elif growth_ratio >= 0.05:
        growth_text = f"{growth_prefix}为 {growth_for_view:.2f}，成长趋势稳健。"
    elif growth_ratio >= 0:
        growth_text = f"{growth_prefix}为 {growth_for_view:.2f}，成长较慢。"
    else:
        growth_text = f"{growth_prefix}为 {growth_for_view:.2f}，收入端存在下滑压力。"

    if pe_for_view is not None and pb_for_view is not None and pe_for_view > 50 and pb_for_view > 10:
        valuation_summary = "估值结论偏谨慎：PE与PB均处高位，安全边际不足。"
    elif pe_for_view is not None and 0 < pe_for_view <= 35 and pb_for_view is not None and pb_for_view <= 4:
        valuation_summary = "估值结论偏合理：PE与PB均未显示明显高估。"
    else:
        valuation_summary = "估值结论中性：部分估值指标缺失或信号不一致。"

    return {
        "score": score,
        "status": fundamental.get("status", "NO_DATA"),
        "source": fundamental.get("source", ""),
        "data_source": fundamental.get("data_source", "ESTIMATED"),
        "message": fundamental.get("message", ""),
        "pe_view": pe_text,
        "pb_view": pb_text,
        "roe_view": roe_text,
        "revenue_growth_view": growth_text,
        "industry_comparison": "行业对比结论：V1当前未取得可靠行业均值，采用绝对估值与盈利质量作保守判断。",
        "valuation_summary": f"{valuation_summary} 基本面{_score_sentence(score)}。",
    }


def explain_sentiment(sentiment: dict[str, Any], score: float | None) -> dict[str, Any]:
    label = metric_value(sentiment.get("sentiment")) or "NEUTRAL"
    message = sentiment.get("message", "")
    news_count = len(sentiment.get("headlines") or [])
    positive_count = 0
    negative_count = 0
    headlines = sentiment.get("headlines") or []

    label_text = {"POSITIVE": "正面", "NEGATIVE": "负面", "NEUTRAL": "中性"}.get(label, "中性")
    if sentiment.get("status") in {"FALLBACK", "COMPLETED"} and not headlines:
        news_text = f"新闻情绪为中性：{message or '新闻接口未返回有效数据'}，使用低置信度fallback。"
        event_text = "事件驱动判断：暂无明确事件驱动。"
    elif news_count == 0:
        news_text = "新闻情绪为中性：当前未获取到有效新闻标题，未发现明显正负面舆情。"
        event_text = "事件驱动判断：暂无明确事件驱动。"
    elif positive_count > negative_count:
        news_text = f"新闻情绪偏正面：共识别 {news_count} 条新闻，其中正面关键词更多。"
        event_text = "事件驱动判断：存在正向事件线索，需要继续跟踪持续性。"
    elif negative_count > positive_count:
        news_text = f"新闻情绪偏负面：共识别 {news_count} 条新闻，其中负面关键词更多。"
        event_text = "事件驱动判断：存在负向事件压力，短线情绪可能承压。"
    else:
        news_text = f"新闻情绪为中性：共识别 {news_count} 条新闻，正负面信号均衡。"
        event_text = "事件驱动判断：未形成单边事件驱动。"

    if news_count >= 5:
        concept_heat = "概念板块热度较高：新闻覆盖数量较多，市场关注度较强。"
    elif news_count > 0:
        concept_heat = "概念板块热度一般：存在新闻覆盖，但热度未明显扩散。"
    else:
        concept_heat = "概念板块热度中性：暂无新闻样本支持热点扩散判断。"

    if label == "POSITIVE":
        market_impact = "市场情绪影响偏正面，可能对短线风险偏好形成支撑。"
    elif label == "NEGATIVE":
        market_impact = "市场情绪影响偏负面，可能压制短线估值和交易情绪。"
    else:
        market_impact = "市场情绪影响中性；若为补全数据，则以低置信度参与最终评分。"

    return {
        "score": score,
        "status": sentiment.get("status", "FALLBACK"),
        "data_source": sentiment.get("data_source", "AI_INFERRED"),
        "confidence": metric_value(sentiment.get("confidence")),
        "news_sentiment": f"{label_text}。{news_text}",
        "concept_heat": concept_heat,
        "market_impact": f"{market_impact} 情绪面{_score_sentence(score)}。",
        "event_driven": event_text,
        "headline_sample": headlines[:3],
    }


def _score_text(score: float | None) -> str:
    return "NO_DATA不参与评分" if score is None else f"{score:.2f}"


def _score_sentence(score: float | None) -> str:
    return "无有效得分，不参与最终加权" if score is None else f"得分 {score:.2f}"


def calculate_sentiment(news: list[str]) -> dict[str, Any]:
    positive = ["增长", "中标", "突破", "回购", "增持", "盈利", "改善", "上调", "创新高", "政策支持"]
    negative = ["处罚", "调查", "减持", "亏损", "召回", "违约", "下滑", "风险", "问询", "退市"]
    pos = sum(any(word in item for word in positive) for item in news)
    neg = sum(any(word in item for word in negative) for item in news)
    label = "positive" if pos > neg else "negative" if neg > pos else "neutral"
    score = float(np.clip(50 + (pos - neg) * 12, 0, 100))
    return {"label": label, "score": round(score, 2), "positive_count": pos, "negative_count": neg, "news_count": len(news), "headlines": news[:5]}


def _percent_to_ratio(value: float | None) -> float | None:
    value = metric_value(value)
    if value is None:
        return None
    return value / 100 if abs(value) > 1 else value


def _num(value: Any) -> float | None:
    value = metric_value(value)
    try:
        if pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)
