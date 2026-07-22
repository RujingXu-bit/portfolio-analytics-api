# Portfolio Analytics — Three-Minute Demo Script

目标成片：1080p、16:9、2:50–3:05。英文口播与屏幕字幕逐句一致；中文仅用于
导演说明和操作提示。所有画面只使用合成演示数据。Provider-backed 片段为录制时
真实成功结果；`/demo` 画面明确标记为 deterministic offline fixture。

## 录制前设置

1. 浏览器使用 1920×1080 视口，缩放 100%，关闭通知和无关标签页。
2. 打开 [Live Demo](https://portfolio-analytics-web-hazel.vercel.app)，只输入合成信息。
3. 预备页签：Landing、`/demo`、合成用户 Portfolio、GitHub Actions 成功页。
4. 若 Provider 失败，不刷新或伪造结果；立即切换 `/demo`，说明它是离线 fixture，
   再展示预录成功片段和 CI 截图。

## 逐秒时间轴与完整英文口播

### 0:00–0:20 — 问题、边界与公开 Demo

镜头：Landing 首屏；光标依次停留在 “Explore the offline demo” 和产品边界文案。

> Portfolio Analytics turns an auditable transaction ledger into explainable historical risk metrics. It is a public engineering demo, not a trading terminal: it does not predict prices, automate trades, or provide investment advice. The offline demo stays available when providers fail.

### 0:20–0:45 — 架构

镜头：切到架构卡片，按 BFF → FastAPI → PostgreSQL/Redis → deterministic domain
的顺序高亮；最后显示 optional LLM 只解释结果。

> The system is a modular monolith. A Next.js BFF keeps the access token inside an HttpOnly cookie. FastAPI coordinates owner-scoped use cases, PostgreSQL stores precise Decimal values, and Redis handles market-data caching and fixed-window rate limits. Financial calculations stay deterministic; an optional language model can only explain their output.

### 0:45–1:25 — 注册、Portfolio、交易与 ledger

镜头：注册页演示公开警告；创建 `Interview Demo`；录入 25,000 USD DEPOSIT 和
50 股 AAPL BUY；停留在两行 ledger。不要显示邮箱、密码或 token。

> Here I register with synthetic information and automatically enter an authenticated session. I create a US-dollar portfolio, then record a cash deposit and an Apple purchase. Each transaction has a stable idempotency reference, so retrying a failed submission cannot double-post the ledger. The backend validates quantities, prices, fees, funding, and ownership. Another user receives the same not-found response as a genuinely missing portfolio. Money stays Decimal through domain boundaries and PostgreSQL NUMERIC in storage, while statistical conversions are explicit, local, and covered by tolerance tests. The browser never reads or stores the API token.

### 1:25–2:05 — 指标、资产权重与 methodology

镜头：显式选择日期并点击 Run analytics；展示四项指标、allocation、`as_of` 和
Provider provenance；展开 methodology，停留在 adjusted close、252 periods、
risk-free rate、cash-flow treatment 和 no-look-ahead alignment。

> Analytics runs only after I choose a date range. The response includes simple return, annualized volatility, maximum drawdown, and the historical Sharpe ratio. The allocation chart combines latest security values with cash. Every result carries an as-of date, a stale flag, and provider provenance. I can open methodology to inspect adjusted close, simple daily returns, 252-period annualization, the dated illustrative risk-free rate, cash-flow treatment, fees, timezone, and no-look-ahead alignment.

### 2:05–2:30 — 风险摘要、回退与历史快照

镜头：点击 Generate risk summary；展示 `Deterministic fallback`、limitations、
免责声明、generator、prompt version 和 newest-first snapshot history。

> Risk summaries are generated only when I request them. The language model never calculates metrics, assigns authority, or changes the risk level. With no DeepSeek key in the public deployment, deterministic risk rules return a bounded explanation, limitations, disclaimer, generator, prompt version, and a persisted historical snapshot.

### 2:30–2:50 — 安全、幂等、CI 与缓存证据

镜头：切到安全/可靠性卡片，再显示 GitHub Actions 成功页。缓存数字只引用仓库中
可复现的 synthetic provider benchmark，不描述为生产容量或 SLA。

> Security is enforced at both layers: HttpOnly sessions in the BFF, owner checks in application services, Argon2 passwords, and HMAC-hashed rate-limit identifiers. Transactions are idempotent. CI tests database migrations, PostgreSQL, Redis, offline financial edge cases, container startup, and cache behavior. The latest quality workflow passes.

### 2:50–3:00 — 限制与入口

镜头：回到结束卡片，显示 Live Demo、backend、frontend 和 release 链接。

> This product explains historical behavior; it does not forecast prices or recommend trades. The live demo, source code, architecture notes, release, and three-minute video are linked from GitHub.

## 断网与 Provider 故障备用镜头

1. 切换到 `/demo`，口头明确：“This is the deterministic offline fixture. It makes
   no provider calls and is not a live result.”
2. 展示固定的四项指标、allocation、risk summary、ledger 和 snapshot provenance。
3. 展示标注为 “PRE-RECORDED PROVIDER SUCCESS” 的成功 analytics 片段。
4. 展示 GitHub Actions 成功页，说明 CI 使用固定 fixture，不依赖外部 Provider。
5. 不把 fixture、缓存旧值或预录片段描述成当前实时 Provider 结果。

## 屏幕字幕

字幕文件：[`demo-video-captions.srt`](demo-video-captions.srt)。字幕文本与上面的
英文口播逐句一致。
