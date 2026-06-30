# A股AI量化分析系统 V1

最小可运行版本，提供股票搜索、单股分析和基础 Top 10 输出。系统只使用真实数据源，不内置模拟行情或伪造股票名称。

## 模块

- Frontend：`/`，股票输入、候选下拉、分析按钮、JSON 结果面板。
- Backend：Flask API。
  - `POST /search_stock`
  - `POST /analyze_stock`
- Data Layer：`data/provider.py`，使用真实行情接口；当前默认走腾讯单股行情/K线以保证响应速度，AkShare/Eastmoney 与配置 `TUSHARE_TOKEN` 后的 Tushare 可作为补充数据源。
- Data Aggregation Layer：`data_aggregator.py`，统一聚合价格、技术面、资金面、基本面、情绪面数据，所有分析模块从同一结构读取。
- Data Completion Engine：`data_completion_engine.py`，在真实数据缺失时使用可解释的计算补全，包括资金流代理、行业均值估算、情绪波动率代理，保证分析链路不断裂。
- Data Trust Layer：所有模块输出 `data_source`，区分 `REAL`、`ESTIMATED`、`AI_INFERRED`，估算值不得覆盖真实字段。

## 本地运行

```bash
pip install -r requirements.txt
python app.py
```

默认地址：

```text
http://127.0.0.1:8000
```

## Render 部署

Render 使用 FastAPI 入口：

```bash
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 10000
```

仓库根目录必须包含：

- `requirements.txt`
- `api.py`
- `runtime.txt`
- `render.yaml`

部署成功后可访问：

- `/docs`
- `/health`
- `POST /top10`
- `POST /analyze`

如果 8000 被占用：

```bash
python -c "from app import app; app.run(host='127.0.0.1', port=8502, debug=False, use_reloader=False)"
```

## API 示例

```bash
curl -X POST http://127.0.0.1:8000/search_stock \
  -H "Content-Type: application/json" \
  -d '{"keyword":"300394"}'
```

```bash
curl -X POST http://127.0.0.1:8000/analyze_stock \
  -H "Content-Type: application/json" \
  -d '{"symbol":"300394"}'
```

```bash
curl -X POST http://127.0.0.1:8000/screen_stocks \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 说明

- 行情、K 线、资金、基本面和新闻均来自真实接口。
- 当真实接口不可达时，API 返回错误或 `null` 字段，不使用模拟数据兜底。
- 资金面缺失时先标记缺口，再由补全引擎使用价格变化、成交量变化和成交额构造 proxy。
- 基本面缺失时先尝试 Tushare/AkShare 财务数据；若仍缺失，只在 `estimated` 字段放板块均值估算，真实 `pe/pb/roe/revenue_growth` 保持 `null`，并标记 `data_source: ESTIMATED`。
- 资金面 proxy 标记 `data_source: ESTIMATED`，并暴露 `proxy_inputs`。
- 情绪面无新闻时使用 `sentiment: NEUTRAL` 加波动率代理补全置信度，并标记 `data_source: AI_INFERRED`。
- 顶层 `data_source` 示例：`{"price":"REAL","kline":"REAL","technical":"REAL","fund_flow":"ESTIMATED","fundamental":"ESTIMATED","sentiment":"AI_INFERRED"}`。
- 如需强制使用 AkShare K线，设置 `MARKET_ENABLE_AK_KLINE=1`；当前默认会在 AkShare K线不可用时使用真实腾讯K线并标记 `FALLBACK`，避免请求静默卡死。
- ROE、营收增长等部分财务字段依赖数据源可用性；配置 `TUSHARE_TOKEN` 后会尝试补齐。
- 本项目仅用于研究和系统开发演示，不构成投资建议。
