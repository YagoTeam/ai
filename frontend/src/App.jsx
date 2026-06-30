import { useEffect, useRef, useState } from "react";
import {
  analyzeStock,
  intradaySignals,
  marketOverview,
  moneyFlowAnomalies,
  portfolioAnalyze,
  healthCheck,
  screenStocks,
  searchStock,
  stockDetail
} from "./api";

const TABS = ["股票分析", "自动选股 Top10", "盘中信号", "主力异动", "我的持仓分析", "大盘分析"];

const LABELS = {
  symbol: "股票代码",
  code: "股票代码",
  name: "股票名称",
  price: "当前价格",
  change_pct: "涨跌幅",
  volume: "成交量",
  score: "综合评分",
  recommendation: "操作建议",
  first_buy_price: "第一手买入",
  second_buy_price: "第二手买入",
  stop_loss_price: "止损价格",
  take_profit_price_1: "第一止盈",
  take_profit_price_2: "第二止盈",
  position_suggestion: "建议仓位",
  entry_reason: "建仓理由",
  risk_reward_ratio: "盈亏比",
  disclaimer: "重要提示",
  market_sentiment: "市场情绪",
  market_sentiment_index: "市场情绪指数",
  risk_appetite: "风险偏好",
  risk_preference: "风险偏好",
  index_trend: "指数趋势",
  status: "状态",
  data_quality: "数据质量",
  data_source_text: "数据来源",
  explanation: "解释",
  pe: "市盈率 PE",
  pb: "市净率 PB",
  roe: "净资产收益率 ROE",
  revenue_growth: "营收增长率",
  net_profit_growth: "净利润增长率",
  gross_margin: "毛利率",
  net_margin: "净利率",
  debt_ratio: "资产负债率",
  signal_type: "信号类型",
  signal_strength: "信号强度",
  reason: "触发原因",
  risk_level: "风险等级",
  anomaly_type: "异动类型",
  money_flow_change: "资金变化",
  volume_spike: "成交量异常",
  action_signal: "行动建议",
  current_price: "当前价格",
  market_value: "当前市值",
  cost_amount: "买入成本",
  floating_profit: "浮盈浮亏",
  floating_profit_ratio: "浮盈浮亏比例",
  position_advice: "持仓建议",
  add_position_price: "补仓参考价",
  reduce_position_price: "减仓参考价",
  next_action: "下一步操作",
};

const VALUE_MAP = {
  REAL: "真实数据",
  ESTIMATED: "估算数据",
  AI_INFERRED: "AI推断",
  COMPLETED: "已完成",
  FALLBACK: "使用备用数据",
  CACHE: "缓存数据",
  OK: "正常",
  PARTIAL: "部分数据",
  HIGH: "高",
  MEDIUM: "中",
  LOW: "低",
  BUY: "买入",
  HOLD: "持有",
  SELL: "卖出",
  WATCH: "观察",
  BREAKOUT: "突破信号",
  ACCUMULATION: "吸筹信号",
  DISTRIBUTION: "派发信号",
  "PANIC SELL": "恐慌抛售",
  "BUY ALERT": "买入预警",
  "SELL ALERT": "卖出预警",
  "price-volume fund-flow proxy": "根据价格和成交量估算资金流",
  "sector-average fundamental completion": "使用行业均值补全基本面",
  "Tencent real K-line API": "腾讯真实K线数据源",
};

const ANALYSIS_STEPS = [
  "正在搜索股票...",
  "正在加载真实行情数据...",
  "正在计算技术指标...",
  "正在生成建仓建议...",
];

function cnValue(value) {
  if (value === null || value === undefined || value === "") return "暂无";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  const text = String(value);
  return VALUE_MAP[text] || text
    .replaceAll("REAL", "真实数据")
    .replaceAll("ESTIMATED", "估算数据")
    .replaceAll("AI_INFERRED", "AI推断")
    .replaceAll("FALLBACK", "使用备用数据")
    .replaceAll("COMPLETED", "已完成")
    .replaceAll("confidence", "置信度")
    .replaceAll("message", "说明")
    .replaceAll("status", "状态")
    .replaceAll("fund flow proxy", "资金流估算");
}

function label(key) {
  return LABELS[key] || "分析项";
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function money(value) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(2)} 元` : "暂无";
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

function StatusBlock({ loading, loadingText, error, empty, emptyText }) {
  if (loading) return <div className="status loading">{loadingText || "服务器正在处理，首次请求可能需要 30-60 秒。"}</div>;
  if (error) return <div className="status error">{error}</div>;
  if (empty) return <div className="status empty">{emptyText}</div>;
  return null;
}

function InfoGrid({ data, fields }) {
  const entries = (fields || Object.keys(data || {})).map((key) => [key, data?.[key]]).filter(([, value]) => value !== undefined);
  if (!entries.length) return <div className="status empty">暂无可靠数据</div>;
  return (
    <div className="info-grid">
      {entries.map(([key, value]) => (
        <div className="info-item" key={key}>
          <span>{label(key)}</span>
          <strong>{Array.isArray(value) || isObject(value) ? <ReadableBlock data={value} /> : cnValue(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function ReadableBlock({ data }) {
  if (!data) return "暂无";
  if (typeof data === "string" || typeof data === "number" || typeof data === "boolean") return cnValue(data);
  if (Array.isArray(data)) {
    if (!data.length) return "暂无";
    return (
      <div className="plain-list">
        {data.slice(0, 8).map((item, index) => (
          <div key={index}>{isObject(item) ? <ReadableBlock data={item} /> : cnValue(item)}</div>
        ))}
      </div>
    );
  }
  const entries = Object.entries(data).filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!entries.length) return "暂无";
  return (
    <div className="plain-list">
      {entries.slice(0, 12).map(([key, value]) => (
        <div key={key}><b>{label(key)}：</b>{isObject(value) || Array.isArray(value) ? <ReadableBlock data={value} /> : cnValue(value)}</div>
      ))}
    </div>
  );
}

function FinalConclusion({ data }) {
  if (!data) return null;
  const conclusion = data.final_conclusion || buildLocalConclusion(data);
  return (
    <div className="conclusion-card">
      <h3>最终结论</h3>
      <p><b>当前股票：</b>{conclusion.stock || data.name || data.symbol}</p>
      <p><b>综合判断：</b>{conclusion.judgement}</p>
      <div className="reason-list">
        <b>核心原因：</b>
        <ol>
          <li>技术面：{conclusion.core_reasons?.technical}</li>
          <li>资金面：{conclusion.core_reasons?.fund_flow}</li>
          <li>基本面：{conclusion.core_reasons?.fundamental}</li>
          <li>情绪面：{conclusion.core_reasons?.sentiment}</li>
        </ol>
      </div>
      <div className="action-grid">
        <div><span>激进型</span><p>{conclusion.actions?.aggressive}</p></div>
        <div><span>稳健型</span><p>{conclusion.actions?.balanced}</p></div>
        <div><span>保守型</span><p>{conclusion.actions?.conservative}</p></div>
      </div>
      <p className="risk-line">{conclusion.risk_warning}</p>
    </div>
  );
}

function EntryPlan({ data }) {
  const plan = data?.entry_plan || buildLocalEntryPlan(data);
  if (!plan) return null;
  return (
    <div className="entry-card">
      <h3>建仓参考</h3>
      <InfoGrid
        data={plan}
        fields={["first_buy_price", "second_buy_price", "stop_loss_price", "take_profit_price_1", "take_profit_price_2", "position_suggestion", "risk_reward_ratio"]}
      />
      <p><b>理由：</b>{cnValue(plan.entry_reason)}</p>
      <p className="risk-line">重要：{cnValue(plan.disclaimer || "这只是辅助分析，不构成投资建议。")}</p>
    </div>
  );
}

function AnalysisPanel({ data }) {
  if (!data) return null;
  return (
    <div className="analysis-panel">
      <InfoGrid data={data} fields={["name", "symbol", "price", "score", "recommendation"]} />
      <FinalConclusion data={data} />
      <EntryPlan data={data} />
      <div className="module-grid">
        <article><h3>技术面分析</h3><ReadableBlock data={data.technical_analysis} /></article>
        <article><h3>资金面分析</h3><ReadableBlock data={data.fund_flow_analysis} /></article>
        <article><h3>基本面分析</h3><InfoGrid data={data.fundamental_analysis || {}} fields={["score", "pe", "pb", "roe", "revenue_growth", "net_profit_growth", "gross_margin", "debt_ratio", "data_quality", "data_source_text", "explanation"]} /></article>
        <article><h3>情绪面分析</h3><ReadableBlock data={data.sentiment_analysis} /></article>
      </div>
    </div>
  );
}

function buildLocalEntryPlan(data) {
  if (!data?.price) return null;
  const price = Number(data.price);
  const score = Number(data.score || 50);
  const first = price * (score >= 75 ? 0.985 : score >= 65 ? 0.97 : 0.94);
  const second = first * (score >= 65 ? 0.95 : 0.92);
  const stop = Math.min(second * 0.95, first * 0.92);
  return {
    first_buy_price: Number(first.toFixed(2)),
    second_buy_price: Number(second.toFixed(2)),
    stop_loss_price: Number(stop.toFixed(2)),
    take_profit_price_1: Number((price * 1.08).toFixed(2)),
    take_profit_price_2: Number((price * 1.16).toFixed(2)),
    position_suggestion: score >= 80 ? "中等仓位" : score >= 65 ? "轻仓" : "暂不建仓",
    entry_reason: "根据当前价格和综合评分估算，等待回踩比追高更稳妥。",
    risk_reward_ratio: "约 1:2",
    disclaimer: "仅为辅助分析，不构成投资建议。"
  };
}

function buildLocalConclusion(data) {
  const plan = data.entry_plan || buildLocalEntryPlan(data) || {};
  const score = Number(data.score || 50);
  const judgement = data.recommendation === "BUY" && score >= 80 ? "可分批建仓" : data.recommendation === "BUY" ? "可轻仓试探" : data.recommendation === "SELL" ? "应该减仓" : "适合观察";
  return {
    stock: data.name || data.symbol,
    judgement,
    core_reasons: {
      technical: "价格趋势需要结合支撑和压力观察，不建议只看一天涨跌。",
      fund_flow: "资金面以是否持续流入为关键，短期波动不单独作为买卖依据。",
      fundamental: "基本面只采用可靠字段，缺失数据不会强行编数字。",
      sentiment: "情绪面偏辅助，重点仍看价格、资金和业绩质量。"
    },
    actions: {
      aggressive: `第一笔可参考 ${plan.first_buy_price || "-"} 元附近。`,
      balanced: `等待回踩确认，第二笔参考 ${plan.second_buy_price || "-"} 元附近。`,
      conservative: "暂时观察，不追高。"
    },
    risk_warning: `若跌破 ${plan.stop_loss_price || "-"} 元，需要重新判断。`
  };
}

function Top10Table({ rows, onDetail }) {
  if (!rows.length) return <StatusBlock empty emptyText="暂无选股结果" />;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>代码</th><th>名称</th><th>价格</th><th>评分</th><th>建议</th><th>行业</th><th>龙头</th><th>风险</th><th>操作</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol || row.code}>
              <td>{row.symbol || row.code}</td>
              <td>{row.name || "待补全"}</td>
              <td>{cnValue(row.price)}</td>
              <td>{cnValue(row.score)}</td>
              <td><span className={`badge ${String(row.recommendation || "").toLowerCase()}`}>{cnValue(row.recommendation)}</span></td>
              <td>{row.sector?.industry || row.sector?.sub_industry || "暂无"}</td>
              <td>{row.is_leader ? "是" : "否"}</td>
              <td><span className={`risk ${String(row.risk_level || "").toLowerCase()}`}>{cnValue(row.risk_level)}</span></td>
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
        <thead><tr><th>股票名称</th><th>股票代码</th><th>所属板块</th><th>信号类型</th><th>信号强度</th><th>触发原因</th><th>风险等级</th></tr></thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.symbol}-${index}`}>
              <td>{row.name || "待补全"}</td>
              <td>{row.symbol || "-"}</td>
              <td>{row.sector?.industry || row.sector?.sub_industry || "暂无"}</td>
              <td><span className={`badge ${String(row.signal_type || "").toLowerCase()}`}>{cnValue(row.signal_type || row.raw_signal_type)}</span></td>
              <td>{cnValue(row.signal_strength)}</td>
              <td>{row.reason || (row.trigger_reason || []).map(cnValue).join("；") || "暂无"}</td>
              <td><span className={`risk ${String(row.risk_level || "").toLowerCase()}`}>{cnValue(row.risk_level)}</span></td>
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
        <thead><tr><th>股票名称</th><th>股票代码</th><th>所属板块</th><th>异动类型</th><th>资金变化</th><th>成交量异常</th><th>行动建议</th></tr></thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.symbol}-${index}`}>
              <td>{row.name || "待补全"}</td>
              <td>{row.symbol || "-"}</td>
              <td>{row.sector?.industry || row.sector?.sub_industry || "暂无"}</td>
              <td>{cnValue(row.anomaly_type)}</td>
              <td>{cnValue(row.money_flow_change)}</td>
              <td>{cnValue(row.volume_spike)}</td>
              <td><span className="badge">{cnValue(row.action_signal)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SearchBox({ keyword, setKeyword, candidates, searching, onPick, onAnalyze, disabled, loadingText }) {
  return (
    <div className="search-area">
      <div className="search-row">
        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="输入股票代码、名称或拼音首字母，例如 300394、德明利、DML"
          onKeyDown={(event) => {
            if (event.key === "Enter") onAnalyze();
          }}
        />
        <button onClick={onAnalyze} disabled={disabled}>{disabled ? "处理中" : "分析"}</button>
      </div>
      {searching ? <div className="status loading">正在搜索股票...</div> : null}
      {disabled ? <div className="progress-line">{loadingText}</div> : null}
      {candidates.length ? (
        <div className="candidate-list">
          {candidates.map((item) => (
            <button className="candidate" key={item.code} onClick={() => onPick(item)}>
              <span>{item.name}</span><b>{item.code}</b>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState(TABS[0]);
  const [keyword, setKeyword] = useState("300394");
  const [selected, setSelected] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [searching, setSearching] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [detail, setDetail] = useState(null);
  const [top10, setTop10] = useState([]);
  const [signals, setSignals] = useState([]);
  const [moneyRows, setMoneyRows] = useState([]);
  const [market, setMarket] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [portfolioForm, setPortfolioForm] = useState({ symbol: "300394", cost_price: "280", shares: "100", available_cash: "20000", max_position_ratio: "0.3", risk_preference: "稳健" });
  const [loading, setLoading] = useState({});
  const [errors, setErrors] = useState({});
  const [stepIndex, setStepIndex] = useState(0);
  const [serverStatus, setServerStatus] = useState({ state: "checking", text: "" });
  const cacheRef = useRef(new Map());

  useEffect(() => {
    let alive = true;
    async function checkServer() {
      setServerStatus((current) => current.state === "ok" ? current : { state: "checking", text: "" });
      try {
        const result = await healthCheck(8000);
        if (!alive) return;
        if (result.ok) {
          setServerStatus({ state: "ok", text: "服务器运行正常" });
        } else {
          setServerStatus({ state: "down", text: "服务器暂时不可用，请稍后重试。" });
        }
      } catch (error) {
        if (!alive) return;
        if (error?.name === "AbortError") {
          setServerStatus({ state: "waking", text: "服务器正在唤醒，首次请求可能需要 30-60 秒。" });
        } else {
          setServerStatus({ state: "down", text: "服务器暂时不可用，请稍后重试。" });
        }
      }
    }
    checkServer();
    const timer = window.setInterval(checkServer, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const query = keyword.trim();
    setSelected(null);
    if (query.length < 2) {
      setCandidates([]);
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const rows = await searchStock(query);
        setCandidates((rows || []).slice(0, 10));
      } catch {
        setCandidates([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  useEffect(() => {
    if (!loading.analysis) return undefined;
    const timer = window.setInterval(() => setStepIndex((index) => Math.min(index + 1, ANALYSIS_STEPS.length - 1)), 900);
    return () => window.clearInterval(timer);
  }, [loading.analysis]);

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
      setError(key, error.message || "请求失败，服务器可能正在唤醒，请稍后重试。");
    } finally {
      setBusy(key, false);
    }
  }

  async function resolveSymbol() {
    const input = keyword.trim();
    if (!input) throw new Error("请输入股票代码或名称");
    if (/[\u4e00-\u9fa5]/.test(input) || /^[A-Z]{2,}$/i.test(input)) {
      const rows = candidates.length ? candidates : await searchStock(input);
      if (!rows.length) throw new Error("没有找到匹配股票");
      setSelected(rows[0]);
      return rows[0].code;
    }
    return input;
  }

  async function handleAnalyze() {
    setStepIndex(0);
    await runAction("analysis", async () => {
      const symbol = await resolveSymbol();
      const cached = cacheRef.current.get(symbol);
      if (cached && Date.now() - cached.ts < 60_000) {
        setAnalysis(cached.data);
        return;
      }
      const result = await analyzeStock(symbol);
      cacheRef.current.set(symbol, { ts: Date.now(), data: result });
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
      setActiveTab("自动选股 Top10");
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
      setMoneyRows(result?.abnormal_stocks?.length ? result.abnormal_stocks : result?.anomalies || []);
    });
  }

  async function handleMarket() {
    await runAction("market", async () => setMarket(await marketOverview()));
  }

  async function handlePortfolio() {
    await runAction("portfolio", async () => {
      const payload = {
        ...portfolioForm,
        cost_price: Number(portfolioForm.cost_price),
        shares: Number(portfolioForm.shares),
        available_cash: Number(portfolioForm.available_cash),
        max_position_ratio: Number(portfolioForm.max_position_ratio),
      };
      const result = await portfolioAnalyze(payload);
      setPortfolio(isObject(result) ? result : {});
    });
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">后端服务：https://ai11.onrender.com</p>
          <h1>A股AI量化投资系统</h1>
        </div>
        {serverStatus.state === "ok" ? null : <div className={`health-pill ${serverStatus.state}`}>{serverStatus.text}</div>}
      </header>

      <nav className="tabs">
        {TABS.map((tab) => (
          <button key={tab} className={activeTab === tab ? "active" : ""} onClick={() => setActiveTab(tab)}>{tab}</button>
        ))}
      </nav>

      <main className="workspace">
        {activeTab === "股票分析" ? (
          <SectionCard title="股票分析">
            <SearchBox
              keyword={keyword}
              setKeyword={setKeyword}
              candidates={candidates}
              searching={searching}
              selected={selected}
              onPick={(item) => {
                setSelected(item);
                setKeyword(item.code);
                setCandidates([]);
              }}
              onAnalyze={handleAnalyze}
              disabled={loading.analysis}
              loadingText={ANALYSIS_STEPS[stepIndex]}
            />
            <StatusBlock loading={loading.analysis} loadingText={ANALYSIS_STEPS[stepIndex]} error={errors.analysis} empty={!analysis && !loading.analysis} emptyText="输入股票后点击分析，系统会生成最终结论和建仓参考。" />
            <AnalysisPanel data={analysis} />
          </SectionCard>
        ) : null}

        {activeTab === "自动选股 Top10" ? (
          <>
            <SectionCard title="自动选股 Top10" actions={<button onClick={handleScreen} disabled={loading.top10}>{loading.top10 ? "扫描中" : "自动选股"}</button>}>
              <StatusBlock loading={loading.top10} loadingText="正在扫描全市场并排序..." error={errors.top10} empty={!top10.length && !loading.top10} emptyText="点击自动选股，获取全市场 Top10 BUY 股票。" />
              {!loading.top10 && !errors.top10 ? <Top10Table rows={top10} onDetail={handleDetail} /> : null}
            </SectionCard>
            <SectionCard title="股票详情">
              <StatusBlock loading={loading.detail} loadingText="正在加载完整分析详情..." error={errors.detail} empty={!detail && !loading.detail} emptyText="点击 Top10 表格里的查看详情。" />
              <AnalysisPanel data={detail} />
            </SectionCard>
          </>
        ) : null}

        {activeTab === "盘中信号" ? (
          <SectionCard title="盘中信号" actions={<button onClick={handleSignals} disabled={loading.signals}>{loading.signals ? "刷新中" : "获取信号"}</button>}>
            <StatusBlock loading={loading.signals} loadingText="正在刷新盘中信号..." error={errors.signals} empty={!signals.length && !loading.signals} emptyText="点击获取信号，查看股票名称、板块和触发原因。" />
            {!loading.signals && !errors.signals ? <SignalTable rows={signals} /> : null}
          </SectionCard>
        ) : null}

        {activeTab === "主力异动" ? (
          <SectionCard title="主力异动" actions={<button onClick={handleMoneyFlow} disabled={loading.money}>{loading.money ? "监控中" : "主力异动监控"}</button>}>
            <StatusBlock loading={loading.money} loadingText="正在检测资金异动..." error={errors.money} empty={!moneyRows.length && !loading.money} emptyText="点击主力异动监控，查看资金变化和行动建议。" />
            {!loading.money && !errors.money ? <MoneyFlowTable rows={moneyRows} /> : null}
          </SectionCard>
        ) : null}

        {activeTab === "我的持仓分析" ? (
          <SectionCard title="我的持仓分析" actions={<button onClick={handlePortfolio} disabled={loading.portfolio}>{loading.portfolio ? "分析中" : "分析持仓"}</button>}>
            <div className="form-grid">
              {[
                ["symbol", "股票代码/名称"],
                ["cost_price", "买入成本"],
                ["shares", "持仓数量"],
                ["available_cash", "当前可用资金"],
                ["max_position_ratio", "计划最大仓位"],
              ].map(([key, text]) => (
                <label key={key}><span>{text}</span><input value={portfolioForm[key]} onChange={(event) => setPortfolioForm((form) => ({ ...form, [key]: event.target.value }))} /></label>
              ))}
              <label><span>风险偏好</span><select value={portfolioForm.risk_preference} onChange={(event) => setPortfolioForm((form) => ({ ...form, risk_preference: event.target.value }))}><option>保守</option><option>稳健</option><option>激进</option></select></label>
            </div>
            <StatusBlock loading={loading.portfolio} loadingText="正在结合当前行情和你的成本分析..." error={errors.portfolio} empty={!portfolio && !loading.portfolio} emptyText="填写成本和仓位后，系统会给出是否持有、补仓、减仓或止损建议。" />
            {portfolio ? (
              <div className="analysis-panel">
                <InfoGrid data={portfolio} fields={["name", "symbol", "current_price", "cost_price", "shares", "market_value", "cost_amount", "floating_profit", "floating_profit_ratio", "position_advice", "add_position_price", "reduce_position_price", "stop_loss_price"]} />
                <div className="conclusion-card"><h3>后续操作建议</h3><p>{portfolio.reason || "暂无可靠数据"}</p><p>{portfolio.next_action || "暂无可靠数据"}</p></div>
              </div>
            ) : null}
          </SectionCard>
        ) : null}

        {activeTab === "大盘分析" ? (
          <SectionCard title="大盘分析" actions={<button onClick={handleMarket} disabled={loading.market}>{loading.market ? "分析中" : "大盘分析"}</button>}>
            <StatusBlock loading={loading.market} loadingText="正在加载指数和板块数据..." error={errors.market} empty={!market && !loading.market} emptyText="点击大盘分析，查看市场情绪、风险偏好和热门板块。" />
            {market ? (
              <div className="market-layout">
                <InfoGrid data={market} fields={["market_sentiment", "market_sentiment_index", "risk_appetite", "index_trend", "status"]} />
                <div className="mini-list">
                  <h3>热门板块</h3>
                  {(market.hot_sectors || []).length ? (market.hot_sectors || []).slice(0, 10).map((item) => <div className="mini-item" key={item.code || item.name}><span>{item.name}</span><strong>{cnValue(item.change_pct)}%</strong></div>) : <div className="status empty">暂无热门板块</div>}
                </div>
              </div>
            ) : null}
          </SectionCard>
        ) : null}
      </main>
    </div>
  );
}
