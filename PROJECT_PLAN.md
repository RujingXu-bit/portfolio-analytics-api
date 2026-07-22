# AI-Powered Portfolio Analytics API：项目总计划

> 本文件是项目范围、任务依赖、优先级和进度的唯一权威来源。执行任何 Task 前先阅读根目录 `AGENTS.md`。只有达到任务验收标准后才能勾选完成。

## 1. 项目概览

### 最终目标

构建一个求职展示级的投资组合分析后端。用户可以创建投资组合、记录交易并获得基于市场数据的可解释金融指标；系统可以选择性调用 LLM，将确定性计算结果转化为风险摘要，但不提供明确买卖建议。

### 时间预算

- 基准周期：5周。
- 工作节奏：每周5天，每天4–5小时。
- 总预算：106–133小时；W2 复核后补入必需的多资产估值任务。
- 缓冲：计划内保留约5个工作日的集成和排错空间。

### 当前状态

- 项目阶段：Week 4 准备开始，W3.1–W3.5 已完成。
- 当前优先任务：`W4.1`。
- 当前阻塞：无。
- V1目标版本：`v1.0.0`。

## 2. 产品范围

### V1必须完成（Must）

- 用户注册、登录和 JWT 身份认证。
- Portfolio 创建与查询。
- BUY、SELL、DEPOSIT、WITHDRAWAL 交易记录。
- PostgreSQL 持久化和 Alembic migration。
- Fake Market Data Provider 和一个真实 Provider。
- 简单收益率、年化波动率、最大回撤、Sharpe Ratio。
- Redis 市场数据缓存。
- 外部调用超时、有限重试和可解释降级。
- 结构化指标响应及 methodology。
- LLM 风险摘要和确定性回退摘要。
- 单元测试、集成测试、CI、Docker Compose 和完整 README。

### 时间充足再完成（Should）

- 第二个真实市场数据 Provider。
- 旧缓存 `stale` 降级策略。
- API 入口限流。
- AnalysisSnapshot 历史查询。
- 轻量负载测试和缓存效果对比。

### V1明确不做（Won't）

- 股票价格或涨跌趋势预测。
- 自动交易和明确买卖建议。
- 完整 Web 或移动端前端。
- 银行 Open Banking 接入。
- 复杂税务、会计或多币种自动换汇。
- 微服务拆分、Kafka、Kubernetes。
- 生产级高可用云部署。

## 3. 目标架构

```text
Client / Swagger
       |
    FastAPI
       |
Application Services ---- Auth / Ownership
   |          |             |
Domain     Repository    Insight Generator
Analytics      |          |          |
   |       PostgreSQL   Rules       LLM
   |
MarketDataProvider ---- Redis Cache
   |          |
 Fake     Real Provider
```

核心原则：金融数值由可测试的确定性代码计算；LLM 只解释结构化结果；外部服务失败不破坏核心数据与分析流程。

## 4. 五周执行计划

### Week 1：工程骨架与金融引擎（20–25小时）

#### [x] W1.1 初始化工程骨架与统一命令（4–5h）

依赖：无。

工作内容：

- 使用 uv 初始化应用项目，固定 Python 版本。
- 建立 `src` layout 和测试目录。
- 配置 `pyproject.toml`、Ruff、mypy、pytest 和 coverage。
- 创建 `Makefile`，至少提供 install、dev、test、lint、format、typecheck、check。
- 创建最小 FastAPI 应用和 health endpoint。
- 创建最小 GitHub Actions 工作流，先运行静态检查和单元测试。

验收标准：

- 新环境可通过文档中的统一命令安装依赖。
- FastAPI health endpoint 可访问。
- Ruff、mypy 和空测试套件可以成功运行。
- `uv.lock` 已生成并纳入版本控制。

#### [x] W1.2 定义领域类型和金融口径（3–4h）

依赖：W1.1。

工作内容：

- 定义 `PriceBar`、领域 `Transaction`、`PortfolioAnalytics`。
- 定义交易类型枚举。
- 确认 adjusted close、简单收益率、252年化周期和无风险利率配置方式。
- 建立 methodology 输出结构。

验收标准：

- 类型通过 mypy。
- 金融假设写入文档和测试 fixture 说明。
- 领域类型不依赖 FastAPI、SQLAlchemy、Pandas 或具体 Provider。

#### [x] W1.3 实现核心金融指标（8–10h）

依赖：W1.2。

工作内容：

- 实现简单收益率。
- 实现年化波动率。
- 实现最大回撤。
- 实现 Sharpe Ratio。
- 明确数据不足、零波动和非法价格的行为。

验收标准：

- 使用可人工复核的小型序列验证结果。
- 覆盖空数据、单点、价格不变、持续下跌、缺失日期和重复日期。
- 计算函数无网络、数据库和系统当前时间依赖。

#### [x] W1.4 完成内存垂直切片（4–6h）

依赖：W1.3。

工作内容：

- 定义 `MarketDataProvider` 协议。
- 实现 `FakeMarketDataProvider`。
- 实现内存 Repository。
- 建立临时 Portfolio 创建和 analytics API。
- 使用 `httpx.AsyncClient + ASGITransport` 编写 API 测试。

验收标准：

- 固定交易与价格数据可以通过 API 返回四项指标和 methodology。
- 单元测试完全离线且结果稳定。
- 路由不直接执行金融算法。

#### [x] W1.R Week 1里程碑审查（2–3h）

依赖：W1.1、W1.2、W1.3、W1.4。

工作内容：

- 根据本计划逐项验证 W1.1–W1.4 的验收标准与完成状态。
- 运行 `make check` 和 `make test-cov`，记录命令、结果及失败原因。
- 审查金融计算正确性、边界测试、领域层依赖边界和单元测试网络隔离。
- 按 P0、P1、P2、P3 输出带文件和行号的问题，并给出 PASS、CONDITIONAL PASS 或 FAIL 结论。

验收标准：

- W1.1–W1.4 的全部验收标准均由当前仓库事实和可复现验证支持。
- `make check` 和 `make test-cov` 均成功运行。
- 不存在未解决的 P0 或 P1 问题，P2 和 P3 问题均已记录处置结论。
- 最终审查结论为 PASS；CONDITIONAL PASS 或 FAIL 均不视为通过，不得勾选本任务。

里程碑门禁：`W1.R` 勾选完成前，不得启动任何 W2 任务。完成审查但结论未通过时保持 `[ ]`，在进度日志记录阻塞项并完成整改后重新审查。

### Week 2：PostgreSQL与交易业务（20–25小时）

#### [x] W2.1 建立本地基础设施（3–4h）

依赖：W1.R。

工作内容：

- 创建 Docker Compose，包含 PostgreSQL 16 和 Redis 7。
- 扩展 Makefile：infra-up、infra-down、infra-logs。
- 创建 `.env.example`，区分开发与测试配置。
- 加入服务健康检查。

验收标准：

- 一条统一命令可启动基础设施。
- 服务健康状态可验证。
- 仓库不包含真实凭据。

#### [x] W2.2 设计数据库模型与首次迁移（6–7h）

依赖：W2.1、W1.2。

工作内容：

- 建立 User、Portfolio、Asset、Transaction 和 AnalysisSnapshot 模型。
- 为金额、价格、数量和费用选择明确的 NUMERIC 精度。
- 添加所有权、唯一性、外键和必要索引。
- 配置 Alembic 并生成首次 migration。

验收标准：

- 空数据库可升级至最新 schema。
- ORM模型与migration一致。
- 金额字段没有使用浮点数据库类型。

#### [x] W2.3 实现 Repository 与交易规则（6–8h）

依赖：W2.2。

工作内容：

- 实现 PostgreSQL Repository。
- 实现交易创建、查询和幂等处理。
- 根据交易流水派生持仓。
- 定义非法交易行为，例如卖出超过持仓。

验收标准：

- Repository 集成测试通过。
- 重复 `external_id` 不会重复记账。
- 测试不依赖执行顺序并可自动清理。

#### [x] W2.4 完成持久化交易垂直切片（5–6h）

依赖：W2.3、W1.4。

工作内容：

- 实现 Portfolio 创建与查询。
- 实现 Transaction 创建与查询。
- 将 analytics 用例切换到数据库 Repository。
- 统一验证错误和领域错误的 HTTP 映射。

验收标准：

- 以下接口完成并有集成测试：
  - `POST /portfolios`
  - `GET /portfolios/{id}`
  - `POST /portfolios/{id}/transactions`
  - `GET /portfolios/{id}/transactions`
  - `GET /portfolios/{id}/analytics`
- 数据在应用重启后仍然存在。

#### [x] W2.R Week 2里程碑审查（2–3h）

依赖：W2.1、W2.2、W2.3、W2.4。

工作内容：

- 根据本计划逐项验证 W2.1–W2.4 的验收标准与完成状态。
- 运行 `make check` 和 `make test-cov`，记录命令、结果及失败原因。
- 审查金融计算正确性与边界测试、领域层依赖边界、测试网络隔离和数据库测试隔离。
- 按 P0、P1、P2、P3 输出带文件和行号的问题，并给出 PASS、CONDITIONAL PASS 或 FAIL 结论。

验收标准：

- W2.1–W2.4 的全部验收标准均由当前仓库事实和可复现验证支持。
- `make check` 和 `make test-cov` 均成功运行，W2 PostgreSQL 集成测试通过。
- 不存在未解决的 P0 或 P1 问题，P2 和 P3 问题均已记录处置结论。
- 最终审查结论为 PASS；CONDITIONAL PASS 或 FAIL 均不视为通过，不得勾选本任务。

里程碑门禁：`W2.R` 勾选完成前，不得启动任何 W3 任务。完成审查但结论未通过时保持 `[ ]`，在进度日志记录阻塞项并完成整改后重新审查。

### Week 3：市场数据、Redis与韧性（26–33小时）

#### [x] W3.1 实现第一个真实 Provider（6–8h）

依赖：W1.4、W2.R。

工作内容：

- 实现 YFinance Provider 或在任务开始时记录选择其他 Provider 的理由。
- 标准化为内部 `PriceBar`。
- 处理 adjusted close、时区、重复日期、空数据和无效 symbol。
- 将阻塞 SDK 调用移出 event loop。

验收标准：

- 应用服务不依赖供应商响应或 DataFrame。
- Provider contract test 可手动运行。
- 普通单元测试和 CI 不访问真实网络。

#### [x] W3.2 实现Redis缓存（5–6h）

依赖：W2.1、W3.1。

工作内容：

- 设计带版本的缓存键。
- 为可能变化的日线范围和已完成历史设置不同 TTL；独立 quote TTL 等真正
  增加 quote 能力时再实现，不扩张当前 V1 API。
- 记录 cache hit/miss。
- 测试序列化、过期和缓存旁路。

验收标准：

- 相同查询在 TTL 内不重复请求 Provider。
- 缓存内容可正确还原为内部类型。
- Redis 失效时可以明确报错或安全回退，不返回损坏数据。

#### [x] W3.3 实现超时、重试与降级（5–6h）

依赖：W3.1、W3.2。

工作内容：

- 设置连接和读取超时。
- 只对适合重试的错误进行有限重试。
- 映射429、5xx、无效symbol和数据不足。
- 可行时实现旧缓存 `stale` 回退。

验收标准：

- 故障通过 Fake Provider 可重复模拟。
- 重试有次数上限且不存在无限等待。
- 返回旧数据时 API 明确标记 `stale`。

#### [x] W3.4 第二Provider决策点（2–4h，可选）

依赖：W3.3。

工作内容：

- 评估剩余时间和 V1 稳定性。
- 时间允许时实现 Finnhub 或其他 REST Provider。
- 否则写入 backlog，不影响 V1 完成。

验收标准：

- 若实现，必须通过同一 Provider contract test。
- Provider 切换通过配置完成，不修改领域或应用逻辑。

#### [x] W3.5 实现多资产组合估值（6–8h）

依赖：W2.4、W3.3。

工作内容：

- 根据交易发生时间重放各标的持仓，构造无前视偏差的每日组合价值序列。
- 明确 DEPOSIT、WITHDRAWAL、交易费用和外部现金流对收益率的处理口径。
- 支持通过同一 MarketDataProvider 获取多个标的的日期对齐价格，并定义缺失价格行为。
- 在 analytics methodology 中记录组合估值、现金流和日期对齐假设。
- 输出可供 W4.3 使用的最新资产权重与集中度输入。

验收标准：

- 固定多资产和现金流 fixture 的组合价值、收益率与权重可人工复核。
- 交易发生前的持仓不会进入历史估值，不使用未来价格或未来交易信息。
- 单标的结果与现有 W2.4 口径保持兼容，缺失价格和无持仓场景有稳定错误。
- 单元测试完全离线，不依赖真实 Provider 或系统当前时间。

### Week 4：认证、权限与AI摘要（20–25小时）

#### [ ] W4.1 实现认证（6–8h）

依赖：W2.2。

工作内容：

- 实现用户注册、登录和密码哈希。
- 签发并验证 JWT access token。
- 统一认证错误响应。

验收标准：

- 不存储或记录明文密码和完整token。
- 注册、成功登录、错误密码和过期token均有测试。

#### [ ] W4.2 实现资源所有权（4–5h）

依赖：W4.1、W2.4。

工作内容：

- 将 Portfolio 和相关资源绑定用户。
- 在查询、修改和分析流程中执行所有权校验。

验收标准：

- 用户A不能读取或修改用户B的任何投资组合资源。
- 所有权测试覆盖直接ID猜测场景。

#### [ ] W4.3 实现确定性风险摘要（3–4h）

依赖：W1.3、W2.4、W3.5。

工作内容：

- 根据波动率、最大回撤、Sharpe Ratio和集中度生成规则摘要。
- 明确数据不足和方法限制。

验收标准：

- 无任何 LLM 或网络服务时仍能生成稳定摘要。
- 摘要不包含明确买卖建议。

#### [ ] W4.4 接入一个LLM Provider（6–8h）

依赖：W4.3。

工作内容：

- 定义 `InsightGenerator` 协议。
- 仅将结构化指标和 methodology 作为输入。
- 使用结构化输出验证响应。
- 加入超时、错误回退和结果缓存。
- AnalysisSnapshot 记录模型与提示词版本。

验收标准：

- LLM失败时返回确定性摘要，核心 analytics 不失败。
- 输出明确包含信息用途和非投资建议声明。
- 单元测试使用 Fake Insight Generator，不调用真实服务。

### Week 5：质量、性能与求职交付（20–25小时）

#### [ ] W5.1 可观测性和安全检查（4–5h）

依赖：W4.4。

工作内容：

- 增加结构化日志和 request ID。
- 检查错误响应与敏感数据脱敏。
- 记录 Provider latency、cache hit/miss 和错误类别。

验收标准：

- 日志不包含密码、JWT或API Key。
- 一次请求可以通过 request ID 追踪主要路径。

#### [ ] W5.2 负载测试与实测指标（4–6h）

依赖：W3.3、W5.1。

工作内容：

- 编写 Locust 或 k6 场景。
- 分别测试冷缓存和热缓存。
- 记录 P50、P95、吞吐量、错误率和缓存命中率。

验收标准：

- 测试环境、数据量、并发和命令可复现。
- README只引用实际测得的数字。
- 不将本地轻量测试描述为生产容量证明。

#### [ ] W5.3 完善CI与干净环境验证（4–5h）

依赖：W2.4、W4.2。

工作内容：

- CI运行 Ruff、format check、mypy、单元测试和集成测试。
- 使用临时 PostgreSQL 和 Redis 服务。
- 验证 Docker 镜像或应用容器构建。

验收标准：

- CI不依赖开发者本机状态或真实第三方 API。
- 从空数据库执行migration并完成集成测试。
- 失败的质量检查会使CI失败。

#### [ ] W5.4 完成README和架构文档（4–5h）

依赖：W5.2、W5.3。

工作内容：

- 完成启动指南、架构图、API示例和环境变量说明。
- 记录金融 methodology、缓存策略和错误降级。
- 写入真实测试覆盖率和性能结果。
- 完善 `docs/architecture.md` 与 `docs/decisions.md`。

验收标准：

- 新用户只看README即可在干净环境启动项目。
- 文档没有未实现功能或虚构指标。

#### [ ] W5.5 发布候选版本与演示准备（3–4h）

依赖：W5.1–W5.4。

工作内容：

- 从干净环境完整走一遍安装、migration、启动和测试。
- 准备三分钟项目演示脚本。
- 准备核心架构与金融口径面试问答。
- 修复发布阻塞问题并创建 `v1.0.0` 候选版本。

验收标准：

- 项目级完成定义全部满足。
- 演示不依赖手工修改数据库或临时补丁。
- 已知限制在README中明确记录。

## 5. 建议API范围

```http
POST /auth/register
POST /auth/login

POST /portfolios
GET  /portfolios
GET  /portfolios/{portfolio_id}

POST /portfolios/{portfolio_id}/transactions
GET  /portfolios/{portfolio_id}/transactions

GET  /portfolios/{portfolio_id}/analytics
POST /portfolios/{portfolio_id}/insights
GET  /portfolios/{portfolio_id}/insights

GET  /health
```

具体响应 schema 在 W1.2 和 W2.4 中确定；不得在没有版本或迁移计划的情况下随意扩张接口。

## 6. 每日工作节奏

每个4–5小时工作日建议按以下方式执行：

1. 20分钟：阅读计划、确认唯一 Task ID 和当日完成标准。
2. 3小时20分钟：实现、测试和小步重构。
3. 30分钟：运行静态检查和对应测试，处理失败。
4. 20分钟：更新文档、计划进度和提交说明。

如果任务未完成，不为了勾选进度而降低验收标准；在进度日志中记录剩余内容，并在下一工作日继续同一 Task。

## 7. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 异步数据库与测试配置耗时 | Week 2延期 | 先完成Repository最小路径，不提前抽象通用框架 |
| 第三方数据源不稳定或限额变化 | 集成测试波动 | Fake Provider作为测试基准，真实测试设为可选 |
| 金融口径不清导致指标返工 | 核心可信度下降 | W1.2先固定methodology并用人工样例验证 |
| JWT与权限边界遗漏 | 数据泄漏风险 | 为跨用户ID访问建立专门负向测试 |
| LLM响应不稳定 | 核心API失败 | 规则摘要先行，LLM永远是可回退适配器 |
| 追求覆盖率或架构展示导致过度设计 | 工期失控 | 以完成定义和V1 Must范围为准 |
| 过早开发前端 | 后端质量下降 | V1只使用Swagger、curl或API客户端演示 |

## 8. Backlog

以下内容不进入当前关键路径：

- Streamlit或轻量Web演示壳。
- Finnhub/Twelve Data第二Provider。
- 基准指数对比和Beta。
- 资产集中度高级分析。
- 多币种和外汇换算。
- CSV交易导入。
- Refresh token与token撤销。
- 云端部署与监控面板。

只有V1关键路径稳定，且修改本文件明确调整优先级后，才能开始 Backlog 项目。

## 9. 进度日志

按时间倒序记录。每条只写事实、验证结果和下一步，不记录未验证的完成声明。

### 2026-07-22

- [x] W3.5 完成无前视偏差的多资产组合估值：按 UTC 交易发生时间重放
  账本，以现金加各标的最新已知 adjusted close 市值构造每日组合价值；
  DEPOSIT、WITHDRAWAL 和未入金 BUY 的资金缺口作为外部现金流，交易费用
  始终减少组合价值和收益。WITHDRAWAL 超过现金时返回稳定错误，不引入隐含
  杠杆。
- 多标的价格并发通过同一 `MarketDataProvider` 获取，估值日期使用观测日并集，
  只前向沿用已经观察到的价格，不使用未来价格；必需标的在请求区间完全无
  数据、无证券持仓或无法形成正组合价值时返回稳定 analytics 错误。API 新增
  Decimal 组合总值、现金余额和以总组合价值（含现金）为分母的最新资产权重，
  可直接供 W4.3 使用。
- 验证：15 项聚焦估值测试通过且该关键领域模块 branch coverage 为 95%；
  PostgreSQL API/Repository 聚焦集成测试 6 项通过；`make check` 通过 Ruff、
  format、mypy（52 个源文件）及 111 项离线单元测试；`make test-all` 共 119 项
  通过，综合 branch coverage 为 93%；`uv lock --check` 与 `git diff --check`
  通过。下一步：执行 `W4.1 实现认证`。

- [x] W3.4 完成第二 Provider 决策：W3.1-W3.3 的真实 Provider、离线 Fake、
  Redis 缓存、有限重试和 stale 降级均已通过验证，但必需的 W3.5 多资产
  估值尚未开始；因此不实现 Finnhub、Twelve Data 或其他第二真实 Provider，
  保持其 Backlog/Should 状态且不阻塞 V1。
- 现有 `MarketDataProvider` 依赖注入边界和共享 contract test 足以支持未来
  Provider；本任务未新增 Provider factory、配置枚举、API、凭据或依赖。
  只有 V1 关键路径稳定且 `PROJECT_PLAN.md` 明确调整优先级后才重启该工作。
- 验证：`make check` 通过，Ruff、format、mypy（50 个源文件）与 95 项离线
  单元测试通过；决策与 Backlog 关键词检查及 `git diff --check` 通过。
  下一步：执行 `W3.5 实现多资产组合估值`。

- [x] W3.3 完成市场数据韧性与明确 stale 降级：Provider 协议返回包含
  `price_bars` 与 `stale` 的内部结果，analytics API 新增顶层必填
  `stale` 布尔值；直接 Provider 与未过期缓存返回 false，仅在可重试故障
  耗尽且后备 payload 验证成功时返回 true。
- yfinance 传输请求使用 10 秒 timeout，整个重试序列受 12 秒 operation
  deadline 约束；最多 3 次尝试，退避为 0.25/0.5 秒。无效/空 symbol 与
  畸形数据不重试，429、5xx/网络错误和 timeout 使用稳定内部错误；没有
  可用 stale 时分别映射为 503、503 和 504，畸形供应商响应映射 502。
- 组合顺序固定为 cache -> retry/deadline -> yfinance。缓存只捕获 retryable
  错误读取 stale；确定性错误、损坏 stale 和 Redis 故障不会返回旧数据。
  Fake Provider、真实 Provider、contract、API 与持久化测试均已适配新协议。
- 验证：52 项聚焦 resilience/cache/API/provider 测试通过；`make check`
  通过，Ruff、format、mypy（50 个源文件）和 95 项离线单元测试通过；
  `make test-all` 共 102 项通过，综合 branch coverage 为 93%；显式真实
  yfinance contract 1 项通过；`uv lock --check` 与 `git diff --check`
  通过。下一步：执行 `W3.4 第二Provider决策点`。

- [x] W3.2 完成 Redis 市场数据缓存：`CachedMarketDataProvider` 使用包含
  schema version、Provider、interval、price basis、symbol 和日期范围的
  版本化键；当前/未来 end date 使用 300 秒 TTL，已完成历史使用 86,400
  秒 TTL，并写入保留 604,800 秒的 stale 后备副本供 W3.3 使用。
- 缓存以 ISO date 和 Decimal 字符串序列化内部 `PriceBar`，读取时重新验证
  查询元数据、顺序、唯一日期和价格不变量。损坏 payload 被忽略并覆盖；
  Redis 读写失败记录 bypass 后安全调用/返回 Provider，不把缓存变成核心
  analytics 的可用性依赖。
- Compose 新增隔离 `redis-test`，集成测试使用唯一 namespace 并只删除自身
  键；异步 Redis client 设置独立 1 秒连接/读取超时，并在应用 lifespan
  关闭。当前协议没有 quote 能力，因此未扩张 V1 API，只区分可变日线与已
  完成历史 TTL。
- 验证：`docker compose config --quiet` 通过；8 项聚焦离线缓存测试和 1 项
  真实 Redis 测试通过；`make test-integration` 7 项通过；`make test-all`
  共 81 项通过，综合 branch coverage 为 93%；`make check` 通过，Ruff、
  format、mypy（48 个源文件）和 74 项单元测试通过；`uv lock --check` 与
  `git diff --check` 通过。下一步：执行 `W3.3 实现超时、重试与降级`。

- [x] W3.1 完成首个真实市场数据适配器：应用使用
  `YFinanceMarketDataProvider` 获取日线数据，阻塞 SDK 调用经
  `asyncio.to_thread` 移出 event loop；显式读取 `Adj Close`，将 inclusive
  end 转换为供应商 exclusive end，并将 exchange-local session date、symbol
  与 Decimal 价格标准化为内部 `PriceBar`。
- 适配器拒绝缺失交易所时区、重复日期、缺失/非有限/非正 adjusted close
  和畸形响应；无效 symbol 与空数据使用稳定内部错误。Pandas、yfinance
  类型和供应商响应均未进入应用或领域层。
- 真实网络 contract test 仅由 `make test-contract` 显式启用，使用 AAPL
  2025-01-02 至 2025-01-10 的固定历史窗口成功通过 1 项；默认 contract
  运行确认跳过网络。`Makefile` 的重复 `test-cov` 已修正，普通测试和 CI
  只运行离线套件。
- 验证：`uv lock --check` 通过；`make check` 与 `make test-cov` 通过，Ruff、
  format、mypy（45 个源文件）及 66 项离线单元测试通过，branch coverage
  为 86%；`git diff --check` 通过。下一步：执行 `W3.2 实现Redis缓存`。

- [x] W2.4 完成持久化交易垂直切片：`POST /portfolios`、`GET /portfolios/{id}`、`POST/GET /portfolios/{id}/transactions` 和 `GET /portfolios/{id}/analytics` 均通过应用服务与请求级 Unit of Work 访问 PostgreSQL；路由不包含 SQL 或金融算法。
- Portfolio 创建与交易创建已分离，Portfolio 保存单一 base currency；交易请求验证字段组合、时区和 Decimal 精度。首次交易创建返回 201，相同幂等重试返回原记录和 200，不同 payload 返回稳定 409；超卖返回稳定 422。应用启动不执行 migration，engine 在 lifespan 关闭。
- Analytics 从持久化交易流水读取当前单标的 symbol，继续返回四项指标、`as_of` 与 methodology；多资产估值未在 W2 提前实现，已新增必需任务 W3.5，并将 W4.3 集中度摘要依赖改为 W3.5。
- 验证：15 项离线 API 单元测试和 2 项持久化 API 集成测试通过；集成测试覆盖五个指定 endpoint、统一错误、幂等状态码，并在关闭首个 engine、创建新 app/engine 后读取相同 Portfolio、Transaction 和 analytics，证明数据不依赖进程内存。`make check` 通过，Ruff、format、mypy（40 个源文件）和 58 项单元测试通过；`make test-all` 共 64 项通过，综合 branch coverage 为 94%；`alembic check` 无新增升级操作；`uv lock --check` 与 `git diff --check` 通过。
- Week 2（W2.1–W2.4）全部完成；下一步：执行 `W3.1 实现第一个真实 Provider`。

- [x] W2.3 完成 Portfolio/Transaction Repository 协议、SQLAlchemy Unit of Work、PostgreSQL adapters、纯领域交易校验和持仓重放；领域层不依赖 SQLAlchemy。
- 交易写入锁定 Portfolio 行，在同一事务中检查 portfolio-scoped `external_id`、重放按 occurred_at/created_at/id 排序的流水、拒绝负持仓并写入；symbol 规范化为大写，带时区时间归一化为 UTC。相同幂等 payload 返回原交易，不同 payload 报冲突；W2 只派生证券持仓，不强制现金充足。
- 验证：17 项聚焦 holdings/transaction service 单元测试通过；3 项 PostgreSQL Repository 集成测试覆盖 Decimal 精度、稳定顺序、串行与并发幂等、并发超卖和自动清理；迁移与 Repository 集成测试共 4 项通过；`make check` 通过，mypy 检查 39 个源文件无问题，53 项单元测试通过；`make test-all` 共 57 项通过，综合 branch coverage 为 96%；`uv lock --check` 与 `git diff --check` 通过。
- 下一步：执行 `W2.4 完成持久化交易垂直切片`。

- [x] W2.2 完成 SQLAlchemy 2.x/asyncpg 异步数据库基线、Pydantic Settings、User/Portfolio/Asset/Transaction/AnalysisSnapshot ORM 模型和首次 Alembic migration；应用启动不会隐式执行 migration。
- 数据口径：价格、现金金额和费用使用 `NUMERIC(20,8)`，数量使用 `NUMERIC(28,12)`；Portfolio owner 外键在认证接入前允许为空；Portfolio 保存三字符单一 base currency；交易幂等唯一约束限定在单个 Portfolio 内。关键选择已记录于 `docs/decisions.md`。
- 验证：隔离 `_test` 数据库从空 public schema 成功执行 `alembic upgrade head`；`alembic check` 报告无新增升级操作；集成测试核对 5 张业务表、NUMERIC 精度、交易 CHECK/唯一约束和 owner 外键；开发数据库成功升级至 `20260722_0001`；`make check` 通过，mypy 检查 32 个源文件无问题，36 项单元测试通过；`make test-integration` 1 项通过；`uv lock --check` 与 `git diff --check` 通过。
- 迁移验证首次运行发现 SQLAlchemy 异步运行时缺少 greenlet，依赖声明已修正为 `sqlalchemy[asyncio]` 并重新锁定，随后空库迁移测试通过。
- 下一步：执行 `W2.3 实现 Repository 与交易规则`。

- [x] W2.1 完成 PostgreSQL 16、Redis 7 和隔离测试 PostgreSQL profile；开发 PostgreSQL 使用命名卷，测试实例使用临时存储，Compose 服务均配置健康检查。
- Makefile 新增 `infra-up`、`infra-down`、`infra-logs`、`infra-check`、`infra-test-up` 与 `infra-test-down`；`.env.example` 明确区分开发、测试数据库和 Redis 的本地无秘密配置。因本机 5432 已被其他服务占用，项目宿主端口使用 55432，测试库使用 55433，容器内仍使用 PostgreSQL 标准端口 5432。
- 验证：`docker compose config --quiet` 通过；开发 PostgreSQL 与 Redis 分别通过 `pg_isready` 和 `PING` 健康检查；测试 PostgreSQL 启动为 healthy；`make infra-down` 后 `portfolio-analytics_postgres-data` 卷仍保留；`make check` 通过，Ruff、format、mypy 和 36 项单元测试通过，branch coverage 为 100%；`git diff --check` 通过。
- 下一步：执行 `W2.2 设计数据库模型与首次迁移`。

- [x] W1.4 完成 `MarketDataProvider` 与 `PortfolioRepository` 协议、`FakeMarketDataProvider`、内存 Repository、Portfolio 创建应用服务和 analytics 应用服务；临时 API 提供 `POST /portfolios` 与 `GET /portfolios/{portfolio_id}/analytics`。
- 固定单标的交易和 adjusted-close 价格可通过 API 返回区间简单收益率、年化波动率、最大回撤、Sharpe Ratio、`as_of` 与完整 methodology；路由只负责 HTTP schema 和应用服务调用，单标的临时限制已记录于 README、methodology 与架构文档。
- API 测试使用官方 `httpx.AsyncClient + ASGITransport`，Fake Provider 和内存 Repository 测试完全离线；开发依赖从缺少 mypy 包元数据的 `httpx2` 更正为官方 `httpx`，`pyproject.toml` 与 `uv.lock` 已同步。
- 验证：`make check` 通过，Ruff 与格式检查无问题，mypy 检查 26 个源文件无问题，pytest 36 项通过且 branch coverage 为 100%；`uv lock --check` 通过；依赖扫描确认 API 层未直接执行金融算法，领域层未依赖框架或基础设施。
- Week 1（W1.1–W1.4）全部完成；下一步：执行 `W2.1 建立本地基础设施`。

- [x] W1.3 完成简单日收益率、样本年化波动率、最大回撤和年化 Sharpe Ratio 的纯函数实现；无风险利率和年化周期均由调用方传入。
- 边界行为已固定并记录于 `docs/methodology.md`：空数据、单点数据、价格不变、持续下跌、缺失日期、重复日期、非正或非有限价格，以及无效年化周期和无风险利率。
- 验证：`make check` 通过，Ruff 与格式检查无问题，mypy 检查 17 个源文件无问题，pytest 23 项通过且 branch coverage 为 100%；依赖扫描确认领域计算未引入网络、数据库或系统当前时间依赖。
- 下一步：执行 `W1.4 完成内存垂直切片`。

- [x] W1.2 完成 `PriceBar`、领域 `Transaction`、`PortfolioAnalytics`、交易类型枚举和 `AnalyticsMethodology` 定义，并公开领域包导入。
- 金融口径已记录于 `docs/methodology.md`：adjusted close、简单日收益率、默认 252 年化周期、可配置无风险利率及 methodology 输出字段；固定测试 fixture 明确标记为示例数据。
- 验证：`make check` 通过，Ruff 与格式检查无问题，mypy 检查 15 个源文件无问题，pytest 7 项通过且 coverage 为 100%；领域目录未引入 FastAPI、SQLAlchemy、Pandas、yfinance 或具体 Provider 依赖。
- 下一步：执行 `W1.3 实现核心金融指标`。

### 2026-07-21

- [x] P0.1 建立 `AGENTS.md`，定义架构、金融、测试、安全和执行规则。
- [x] P0.2 建立 `PROJECT_PLAN.md`，确定5周范围、依赖和验收标准。
- [x] W1.1 完成 uv 工程初始化、Python 3.12 固定、src/test 目录、质量工具、统一 Makefile、FastAPI health endpoint 和最小 CI 工作流。
- 验证：全新临时环境执行 `make install` 成功；`make check` 通过，mypy 检查 12 个源文件无问题，pytest 1 项通过且 coverage 为 100%；`GET /health` 返回 200。
- 下一步：执行 `W1.2 定义领域类型和金融口径`。
