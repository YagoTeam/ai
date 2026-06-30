import { useMemo, useState } from "react";
import {
  analyzeStock,
  intradaySignals,
  marketOverview,
  moneyFlowAnomalies,
  screenStocks,
  searchStock,
  stockDetail
} from "./api";

const FIELD_LABELS = {
  symbol: "代码",
  code: "代码",
  name: "名称",
  price: "价格",
  score: "评分",
  recommendation: "建议",
  technical_analysis: "技术面分析",
  fund_flow_analysis: "资金面分析",
  fundamental_analysis: "基本面分析",
  sentiment_analysis: "情绪面分析",
  final_reason: "最终理由",
  data_source: "数据来源",
  value: "指标",
  confidence: "置信度",
  source: "来源",
  timeframe: "周期",
  valid: "有效",
  market_sentiment: "市场情绪",
  risk_appetite: "风险偏好",
  risk_preference: "风险偏好",
  index_trend: "指数趋势",
  hot_sectors: "热门板块",
  signal_type: "信号类型",
  raw_signal_type: "原始信号",
  signal_strength: "信号强度",
  reason: "原因",
  risk_level: "风险等级",
  anomaly_type: "异动类型",
  money_flow_change: "资金变化",
  volume_spike: "成交量异常",
  action_signal: "行动建议"
};

function labelFor(key) {
  return FIELD_LABELS[key] || key.replaceAll("_", " ");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(2);
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function SectionCard({ title, actions, children }) {
  return (
    <section className="section-card">
      <div className="section-head">
        <h2>{title}</h2>
        {actions ? <div className="section-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

function StatusBlock({ loading, error, empty, emptyText = "暂无数据" }) {
  if (loading) return <div className="status loading">正在加载真实数据...</div>;
  if (error) return <div className="status error">{error}</div>;
  if (empty) return <div className="status empty">{emptyText}</div>;
  return null;
}

function KeyValueGrid({ data, compact = false }) {
  if (!data || Object.keys(data).length === 0) return <div className="status empty">暂无可展示内容</div>;
  return (
    <div className={compact ? "kv-grid compact" : "kv-grid"}>
      {Object.entries(data).map(([key, value]) => (
        <div className="kv-item" key={key}>
          <span>{labelFor(key)}</span>
          <strong>{Array.isArray(value) || isObject(value) ? <NestedValue value={value} /> : formatValue(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function NestedValue({ value }) {
  if (Array.isArray(value)) {
    if (!value.length) return "-";
    return (
      <div className="nested-list">
        {value.slice(0, 8).map((item, index) => (
          <div key={`${index}-${typeof item}`}>{isObject(item) ? <KeyValueGrid data={item} compact /> : formatValue(item)}</div>
        ))}
      </div>
    );
  }
  if (isObject(value)) return <KeyValueGrid data={value} compact />;
  return formatValue(value);
}

function AnalysisPanel({ data }) {
  if (!data) return null;
  const summary = {
    name: data.name,
    symbol: data.symbol,
    price: data.price,
    score: data.score,
    recommendation: data.recommendation
  };
  return (
    <div className="analysis-panel">
      <KeyValueGrid data={summary} />
      <div className="analysis-modules">
        <article>
          <h3>技术面分析</h3>
          <NestedValue value={data.technical_analysis} />
        </article>
        <article>
          <h3>资金面分析</h3>
          <NestedValue value={data.fund_flow_analysis} />
        </article>
        <article>
          <h3>基本面分析</h3>
          <NestedValue value={data.fundamental_analysis} />
        </article>
        <article>
          <h3>情绪面分析</h3>
          <NestedValue value={data.sentiment_analysis} />
        </article>
      </div>
      <div className="final-reason">
        <span>最终理由</span>
        <p>{formatValue(data.final_reason)}</p>
      </div>
    </div>
  );
}

function Top10Table({ rows, onDetail }) {
  if (!rows.length) return <StatusBlock empty emptyText="暂无选股结果" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th>价格</th>
            <th>评分</th>
            <th>建议</th>
            <th>行业</th>
            <th>龙头</th>
            <th>风险</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol || row.code}>
              <td>{row.symbol || row.code}</td>
              <td>{row.name || "-"}</td>
              <td>{formatValue(row.price)}</td>
              <td>{formatValue(row.score)}</td>
              <td><span className={`badge ${String(row.recommendation || "").toLowerCase()}`}>{row.recommendation || "-"}</span></td>
              <td>{row.sector?.industry || row.sector?.sub_industry || "-"}</td>
              <td>{row.is_leader ? "是" : "否"}</td>
              <td><span className={`risk ${String(row.risk_level || "").toLowerCase()}`}>{row.risk_level || "-"}</span></td>
              <td><button className="link-btn" onClick={() => onDetail(row.symbol || row.code)}>查看详情</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SignalTable({ rows }) {
  if (!rows.length) return <StatusBlock empty emptyText="暂无盘中信号" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>股票代码</th>
            <th>信号类型</th>
            <th>信号强度</th>
            <th>原因</th>
            <th>风险等级</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.symbol}-${index}`}>
              <td>{row.symbol || "-"}</td>
              <td><span className={`badge ${String(row.signal_type || "").toLowerCase()}`}>{row.signal_type || row.raw_signal_type || "-"}</span></td>
              <td>{formatValue(row.signal_strength)}</td>
              <td>{row.reason || (row.trigger_reason || []).join("；") || "-"}</td>
              <td><span className={`risk ${String(row.risk_level || "").toLowerCase()}`}>{row.risk_level || "-"}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MoneyFlowTable({ rows }) {
  if (!rows.length) return <StatusBlock empty emptyText="暂无主力异动" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>异动股票</th>
            <th>异动类型</th>
            <th>资金变化</th>
            <th>成交量异常</th>
            <th>行动建议</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.symbol}-${index}`}>
              <td>{row.symbol || "-"}</td>
              <td>{row.anomaly_type || "-"}</td>
              <td>{formatValue(row.money_flow_change)}</td>
              <td>{formatValue(row.volume_spike)}</td>
              <td><span className={`badge ${String(row.action_signal || "").toLowerCase().replaceAll(" ", "-")}`}>{row.action_signal || "-"}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [keyword, setKeyword] = useState("300394");
  const [analysis, setAnalysis] = useState(null);
  const [top10, setTop10] = useState([]);
  const [detail, setDetail] = useState(null);
  const [market, setMarket] = useState(null);
  const [signals, setSignals] = useState([]);
  const [moneyRows, setMoneyRows] = useState([]);
  const [loading, setLoading] = useState({});
  const [errors, setErrors] = useState({});

  const hasAnyData = useMemo(() => analysis || top10.length || market || signals.length || moneyRows.length, [analysis, top10, market, signals, moneyRows]);

  function setBusy(key, value) {
    setLoading((current) => ({ ...current, [key]: value }));
  }

  function setError(key, value) {
    setErrors((current) => ({ ...current, [key]: value }));
  }

  async function runAction(key, action) {
    setBusy(key, true);
    setError(key, "");
    try {
      await action();
    } catch (error) {
      setError(key, error.message || "请求失败，请稍后重试");
    } finally {
      setBusy(key, false);
    }
  }

  async function handleAnalyze() {
    const input = keyword.trim();
    if (!input) {
      setError("analysis", "请输入股票代码或名称");
      return;
    }
    await runAction("analysis", async () => {
      let symbol = input;
      if (/[\u4e00-\u9fa5]/.test(input)) {
        const candidates = await searchStock(input);
        if (!candidates.length) throw new Error("没有找到匹配股票");
        symbol = candidates[0].code || candidates[0].symbol;
      }
      const result = await analyzeStock(symbol);
      setAnalysis(result);
    });
  }

  async function handleScreen() {
    await runAction("top10", async () => {
      const rows = await screenStocks(10);
      setTop10(Array.isArray(rows) ? rows : []);
    });
  }

  async function handleDetail(symbol) {
    await runAction("detail", async () => {
      const result = await stockDetail(symbol);
      setDetail(result);
      window.setTimeout(() => document.getElementById("stock-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }), 20);
    });
  }

  async function handleMarket() {
    await runAction("market", async () => {
      setMarket(await marketOverview());
    });
  }

  async function handleSignals() {
    await runAction("signals", async () => {
      const result = await intradaySignals();
      setSignals(result?.signals || []);
    });
  }

  async function handleMoneyFlow() {
    await runAction("money", async () => {
      const result = await moneyFlowAnomalies();
      const rows = result?.abnormal_stocks?.length ? result.abnormal_stocks : result?.anomalies || [];
      setMoneyRows(rows);
    });
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Render API: https://ai11.onrender.com</p>
          <h1>A股AI量化投资系统</h1>
        </div>
        <div className="health-pill">生产 API 已连接</div>
      </header>

      <main className="workspace">
        <SectionCard title="股票分析">
          <div className="search-row">
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="输入股票代码或名称，例如 300394 或 天孚通信"
              onKeyDown={(event) => {
                if (event.key === "Enter") handleAnalyze();
              }}
            />
            <button onClick={handleAnalyze} disabled={loading.analysis}>{loading.analysis ? "分析中" : "分析"}</button>
          </div>
          <StatusBlock loading={loading.analysis} error={errors.analysis} empty={!analysis && !loading.analysis} emptyText="输入股票后点击分析，查看量化解释结果" />
          <AnalysisPanel data={analysis} />
        </SectionCard>

        <SectionCard
          title="Top10 自动选股"
          actions={<button onClick={handleScreen} disabled={loading.top10}>{loading.top10 ? "扫描中" : "自动选股"}</button>}
        >
          <StatusBlock loading={loading.top10} error={errors.top10} empty={!top10.length && !loading.top10} emptyText="点击自动选股，获取全市场 Top10 BUY 股票" />
          {!loading.top10 && !errors.top10 ? <Top10Table rows={top10} onDetail={handleDetail} /> : null}
        </SectionCard>

        <SectionCard
          title="股票详情"
          actions={detail ? <button className="ghost-btn" onClick={() => setDetail(null)}>清空详情</button> : null}
        >
          <div id="stock-detail" />
          <StatusBlock loading={loading.detail} error={errors.detail} empty={!detail && !loading.detail} emptyText="在 Top10 表格中点击查看详情" />
          <AnalysisPanel data={detail} />
        </SectionCard>

        <div className="split-grid">
          <SectionCard
            title="大盘分析"
            actions={<button onClick={handleMarket} disabled={loading.market}>{loading.market ? "分析中" : "大盘分析"}</button>}
          >
            <StatusBlock loading={loading.market} error={errors.market} empty={!market && !loading.market} emptyText="点击大盘分析，查看市场情绪与热门板块" />
            {market ? (
              <div className="market-layout">
                <KeyValueGrid
                  data={{
                    market_sentiment: market.market_sentiment,
                    risk_appetite: market.risk_appetite || market.risk_preference,
                    index_trend: market.index_trend,
                    status: market.status
                  }}
                />
                <div className="mini-list">
                  <h3>热门板块</h3>
                  {(market.hot_sectors || []).length ? (
                    (market.hot_sectors || []).slice(0, 8).map((sector) => (
                      <div className="mini-item" key={sector.code || sector.name}>
                        <span>{sector.name}</span>
                        <strong>{formatValue(sector.change_pct)}%</strong>
                      </div>
                    ))
                  ) : (
                    <div className="status empty">暂无热门板块</div>
                  )}
                </div>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard
            title="盘中信号"
            actions={<button onClick={handleSignals} disabled={loading.signals}>{loading.signals ? "刷新中" : "获取信号"}</button>}
          >
            <StatusBlock loading={loading.signals} error={errors.signals} empty={!signals.length && !loading.signals} emptyText="点击获取信号，查看盘中交易提示" />
            {!loading.signals && !errors.signals ? <SignalTable rows={signals} /> : null}
          </SectionCard>
        </div>

        <SectionCard
          title="主力异动"
          actions={<button onClick={handleMoneyFlow} disabled={loading.money}>{loading.money ? "监控中" : "主力异动监控"}</button>}
        >
          <StatusBlock loading={loading.money} error={errors.money} empty={!moneyRows.length && !loading.money} emptyText="点击主力异动监控，查看资金变化和行动建议" />
          {!loading.money && !errors.money ? <MoneyFlowTable rows={moneyRows} /> : null}
        </SectionCard>

        {!hasAnyData ? <div className="welcome-note">从股票分析或自动选股开始，系统会调用 Render 后端实时获取数据。</div> : null}
      </main>
    </div>
  );
}
