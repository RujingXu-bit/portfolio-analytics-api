# Ledger Lens：项目总计划

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

- 项目阶段：后端 `v1.2.0`、公开演示、Post-V1 P2 增强及前端 CSV 导入均已
  完成；正在统一作品品牌为 `Ledger Lens`。
- 当前优先任务：`F2.2 Ledger Lens 品牌统一`。
- 当前阻塞：无。
- V1目标版本：`v1.0.0`。
- Post-V1 后端当前正式版：`v1.2.0`；独立 Web
  前端当前正式版：`v1.0.0`。

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

依赖：W2.4、W3.3、W3.R。

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

#### [x] W4.1 实现认证（6–8h）

依赖：W2.2。

工作内容：

- 实现用户注册、登录和密码哈希。
- 签发并验证 JWT access token。
- 统一认证错误响应。

验收标准：

- 不存储或记录明文密码和完整token。
- 注册、成功登录、错误密码和过期token均有测试。

#### [x] W4.2 实现资源所有权（4–5h）

依赖：W4.1、W2.4。

工作内容：

- 将 Portfolio 和相关资源绑定用户。
- 在查询、修改和分析流程中执行所有权校验。

验收标准：

- 用户A不能读取或修改用户B的任何投资组合资源。
- 所有权测试覆盖直接ID猜测场景。

#### [x] W4.3 实现确定性风险摘要（3–4h）

依赖：W1.3、W2.4、W3.5。

工作内容：

- 根据波动率、最大回撤、Sharpe Ratio和集中度生成规则摘要。
- 明确数据不足和方法限制。

验收标准：

- 无任何 LLM 或网络服务时仍能生成稳定摘要。
- 摘要不包含明确买卖建议。

#### [x] W4.4 接入一个LLM Provider（6–8h）

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

#### [x] W4.R Week 4里程碑审查（2–3h）

依赖：W4.1、W4.2、W4.3、W4.4。

工作内容：

- 根据本计划逐项验证 W4.1–W4.4 的验收标准与完成状态。
- 运行 `make check` 和 `make test-cov`，记录命令、结果及失败原因。
- 审查金融计算正确性与边界测试、领域层依赖边界、测试网络隔离、认证与所有权边界，以及 LLM 失败回退和快照记录。
- 按 P0、P1、P2、P3 输出带文件和行号的问题，并给出 PASS、CONDITIONAL PASS 或 FAIL 结论。

验收标准：

- W4.1–W4.4 的全部验收标准均由当前仓库事实和可复现验证支持。
- `make check` 和 `make test-cov` 均成功运行，W4 PostgreSQL/Redis 集成测试通过。
- 不存在未解决的 P0 或 P1 问题，P2 和 P3 问题均已记录处置结论。
- 最终审查结论为 PASS；CONDITIONAL PASS 或 FAIL 均不视为通过，不得勾选本任务。

里程碑门禁：`W4.R` 勾选完成前，不得启动任何 W5 任务。完成审查但结论未通过时保持 `[ ]`，在进度日志记录阻塞项并完成整改后重新审查。

### Week 5：质量、性能与求职交付（20–25小时）

#### [x] W5.1 可观测性和安全检查（4–5h）

依赖：W4.R。

工作内容：

- 增加结构化日志和 request ID。
- 检查错误响应与敏感数据脱敏。
- 记录 Provider latency、cache hit/miss 和错误类别。

验收标准：

- 日志不包含密码、JWT或API Key。
- 一次请求可以通过 request ID 追踪主要路径。

#### [x] W5.2 负载测试与实测指标（4–6h）

依赖：W3.3、W5.1。

工作内容：

- 编写 Locust 或 k6 场景。
- 分别测试冷缓存和热缓存。
- 记录 P50、P95、吞吐量、错误率和缓存命中率。

验收标准：

- 测试环境、数据量、并发和命令可复现。
- README只引用实际测得的数字。
- 不将本地轻量测试描述为生产容量证明。

#### [x] W5.3 完善CI与干净环境验证（4–5h）

依赖：W2.4、W4.2、W4.R。

工作内容：

- CI运行 Ruff、format check、mypy、单元测试和集成测试。
- 使用临时 PostgreSQL 和 Redis 服务。
- 验证 Docker 镜像或应用容器构建。

验收标准：

- CI不依赖开发者本机状态或真实第三方 API。
- 从空数据库执行migration并完成集成测试。
- 失败的质量检查会使CI失败。

#### [x] W5.4 完成README和架构文档（4–5h）

依赖：W5.2、W5.3。

工作内容：

- 完成启动指南、架构图、API示例和环境变量说明。
- 记录金融 methodology、缓存策略和错误降级。
- 写入真实测试覆盖率和性能结果。
- 完善 `docs/architecture.md` 与 `docs/decisions.md`。

验收标准：

- 新用户只看README即可在干净环境启动项目。
- 文档没有未实现功能或虚构指标。

#### [x] W5.5 发布候选版本与演示准备（3–4h）

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

#### [x] W5.R Week 5里程碑审查（2–3h）

依赖：W5.1、W5.2、W5.3、W5.4、W5.5。

工作内容：

- 根据本计划逐项验证 W5.1–W5.5 的验收标准与完成状态。
- 运行 `make check` 和 `make test-cov`，记录命令、结果及失败原因。
- 审查金融计算正确性、边界测试、领域层依赖边界和测试网络隔离。
- 按 P0、P1、P2、P3 输出带文件和行号的问题，并给出 PASS、CONDITIONAL PASS 或 FAIL 结论。

验收标准：

- W5.1–W5.5 的全部验收标准均由当前仓库事实和可复现验证支持。
- `make check` 和 `make test-cov` 均成功运行。
- 不存在未解决的 P0 或 P1 问题，P2 和 P3 问题均已记录处置结论。
- 最终审查结论为 PASS；CONDITIONAL PASS 或 FAIL 均不视为通过，不得勾选本任务。

里程碑门禁：`W5.R` 勾选完成前，不得将 V1 候选版本认定为通过里程碑验收。完成审查但结论未通过时保持 `[ ]`，在进度日志记录阻塞项并完成整改后重新审查。

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

## 8. Post-V1 发布与增强计划

Post-V1 工作按下列门禁顺序执行。每次只处理一个 Task ID；前一任务达到验收
标准、通过相应验证并更新本文件后，才能开始下一任务。

### P0：正式发布

#### [x] R1.1 建立 Post-V1 路线图与验收门禁（1–2h）

依赖：W5.R。

验收标准：本文件明确任务顺序、依赖、范围、版本边界和完成条件；不把尚未
实施或发布的能力写成当前事实。

#### [x] R1.2 发布后端正式版 v1.0.0（5–7h）

依赖：R1.1。

工作内容：从最新、干净的 `origin/main` 验证候选版本；将 Python 包版本升级
为 `1.0.0`；同步 changelog、README 和发布状态；运行完整质量、集成、镜像和
构建门禁；创建并发布 annotated `v1.0.0` tag 和非 prerelease GitHub Release；
只清理已经合并的功能分支。

验收标准：本地 HEAD 与目标远端一致，全部发布门禁通过，Git tag 和 GitHub
Release 指向同一已验证提交；未合并分支和版本 tags 未被删除。

### P1：公开全栈演示

#### [x] E1.1 Portfolio 与 AnalysisSnapshot 查询接口（10–14h）

依赖：R1.2。

工作内容：实现所有者范围内、稳定排序、`limit`/`offset` 分页的
`GET /portfolios` 与 `GET /portfolios/{id}/insights`；历史响应只读取当前已
持久化的 snapshot 字段，不新增 migration。

验收标准：分页结构为 `items/total/limit/offset`，Portfolio 按创建时间倒序，
snapshot 按生成时间倒序；跨用户 ID 访问不泄漏资源存在性；旧 snapshot 可读；
OpenAPI、README、架构文档、离线测试和 PostgreSQL 集成测试同步通过。

#### [x] E1.2 公网限流、部署配置与后端 v1.1.0（10–14h）

依赖：E1.1。

工作内容：使用 Redis 固定窗口限制认证、analytics、insights 和普通认证请求；
返回统一 429 与 `Retry-After`；限流 key 和日志不保存秘密或明文邮箱；Redis
故障时记录 bypass 并保持核心路径可用；补齐 Render/Neon/Upstash 部署配置，
完成后发布后端 `v1.1.0`。

验收标准：配置化阈值、边界并发、过期、错误映射、故障降级和脱敏测试通过；
空库 migration、完整检查、集成测试及非 root 镜像通过；公开部署不配置可选
LLM 凭据也能返回确定性摘要。

#### [x] F1.1 独立 Next.js 前端与 BFF 认证边界（10–14h）

依赖：E1.2。

工作内容：在独立 `portfolio-analytics-web` 仓库建立 Node.js 24、Next.js 16、
TypeScript、pnpm、Tailwind 和测试基线；固定后端 v1.1.0 OpenAPI snapshot；通过
Route Handlers 代理允许的后端路径，并以 HttpOnly/Secure/SameSite Cookie
保存短期 access token。

验收标准：浏览器 JavaScript、Local Storage、页面和客户端日志均无法读取
token；私有响应不缓存，写请求执行同源校验，401 清除会话；前端 lint、类型、
单元测试和 production build 通过。

#### [x] F1.2 完整演示闭环 UI（20–28h）

依赖：F1.1。

工作内容：完成英文 Landing、离线 fixture 演示、注册登录、Portfolio 列表/
创建、条件化交易表单与 ledger、显式日期分析、资产权重、methodology、stale
状态、风险摘要和 snapshot 历史页面；不实现编辑删除、预测或自动交易。

验收标准：新用户可从注册完整走到历史查询；真实与 fixture 数据明确分离；
375/768/1440px 布局、键盘路径、错误/空/加载/限流状态及 Playwright 主流程通过。

#### [x] D1.1 低成本公开部署与公网验收（6–10h）

依赖：F1.2。

工作内容：Vercel 托管前端，Render Starter 运行常驻 Docker API，Neon 托管
PostgreSQL，Upstash 托管 Redis；同区部署、独立 migration、健康检查和秘密
配置；公开页面声明仅供演示且数据可能重置。

验收标准：新访客从公开 URL 完成 fixture 浏览和真实注册闭环；日志无秘密；
部署回滚与数据库迁移步骤可复现；不把第三方免费额度描述为 SLA。

#### [x] M1.1 视频、字幕与求职作品包装（8–12h）

依赖：D1.1。

工作内容：生成中文操作提示加英文口播/字幕的三分钟全栈脚本和 SRT；准备明确
标记的离线备用素材；录制 1080p 成片；完善 README 首屏、截图、Live Demo、
视频、前端仓库、GitHub 元数据和简历链接。

验收标准：成片 2:50–3:05、英文口播约 360–400 词；连续三次彩排通过并验证
一次 Provider 故障讲解；所有公开链接有效，功能、覆盖率和性能陈述均可复现。

### P2：公开演示稳定后的可选增强

#### [x] E2.1 第二真实 Market Data Provider（8–12h）

依赖：M1.1。通过现有协议、配置切换和同一 contract test 接入，不改变领域层。

实现：新增异步 Twelve Data `time_series` 适配器，以 `interval=1day`、
`adjust=all` 和显式日期边界获取拆股/分红调整价格；通过
`MARKET_DATA_PROVIDER` 在 `yfinance`/`twelve_data` 间显式选择，后者仅从
`TWELVE_DATA_API_KEY` 读取凭据。复用现有 observation、重试/总 deadline、Redis
缓存与 stale 边界；provider 名称隔离日志和 cache key，不加入隐式 failover。

验收：两个真实适配器通过同一 `PriceBar` contract；Twelve Data 对超时、网络、
429、5xx、无 symbol 和畸形响应映射稳定内部错误；正常 CI 离线且 API key 不进入
日志、缓存或仓库。Ruff、mypy、单元/集成、真实 opt-in contract、迁移漂移、锁文件
和生产镜像 smoke 均通过。

#### [x] E2.2 CSV 交易导入（12–18h）

依赖：M1.1。先预览和逐行验证，再使用稳定 `external_id` 提交；部分失败可解释，
不得绕过所有权、Decimal、交易校验或幂等边界。

实现：新增两个 owner-scoped `text/csv` 接口，preview 只读模拟并逐行返回
`ready`/`replay`/`invalid`，commit 自上而下通过原 `TransactionService` 逐行返回
`created`/`replayed`/`failed`。CSV 必须提供稳定 `external_id`；支持 UTF-8/BOM、
严格 quoting、1,000,000 bytes/500 非空行上限及结构化行错误，不新增数据库迁移。

验收：无权用户在解析前获得一致 404；preview 不写数据；commit 的有效行保留
Portfolio lock、Decimal 精度、领域/持仓验证和数据库唯一约束；格式/字段/ledger/
幂等冲突均可解释，完全重试返回原数据库 transaction ID。单元、PostgreSQL 集成、
OpenAPI、迁移漂移、锁文件及生产镜像门禁全部通过。

#### [x] R2.1 Post-V1/P2 最终审查（2–3h）

依赖：E2.1、E2.2。

工作内容：从最新、干净的 `origin/main` 逐项复核 E2.1/E2.2 的实现、测试、
文档、安全和公网行为；运行静态、单元、集成、迁移、锁文件、构建、真实
Provider contract 与生产镜像门禁；按 P0/P1/P2/P3 输出问题和 PASS、
CONDITIONAL PASS 或 FAIL 结论。

验收：审查基线满足 `HEAD == origin/main` 且工作区干净；E2.1 不会对请求日期
范围静默返回不完整价格序列，E2.2 的所有权、预览只读、Decimal、逐行提交和
幂等边界由离线、PostgreSQL 与公网证据共同支持；全部门禁通过且不存在未解决的
P0/P1 问题。只有最终结论为 PASS 才能勾选本任务并开始正式版本化 E2.x。

#### [x] R2.2 发布后端 v1.2.0（3–5h）

依赖：R2.1。

工作内容：从最新、干净的 `origin/main` 将 Python 包和 FastAPI OpenAPI 版本升级
为 `1.2.0`；把 E2.1、E2.2 与 R2.1 修复从 changelog 的 Unreleased 发布为
`1.2.0`，同步 README 与项目状态；运行完整静态、单元、集成、迁移、锁文件、
构建、真实 Provider contract 和生产镜像门禁；合并发布提交后创建 annotated
`v1.2.0` tag 与非 prerelease GitHub Release。

验收：发布提交来自通过 R2.1 的最新 `origin/main`；wheel、sdist 与 OpenAPI 均
报告 `1.2.0`；全部门禁和发布提交的 GitHub Actions 通过；annotated tag 与 GitHub
Release 指向同一个已验证提交，Release 非 draft、非 prerelease，且发布说明准确
描述第二 Provider、CSV 导入和长窗口 fail-closed 限制。

#### [x] F2.1 前端 CSV 交易导入 UI（8–12h）

依赖：R2.2。

工作内容：将独立前端固定 OpenAPI snapshot 从后端 `v1.1.0` 更新为 `v1.2.0`，
只为 owner-scoped CSV preview/commit 路径扩展 BFF allowlist；BFF 以原始
`text/csv` 字节转发请求，继续执行同源写入校验、HttpOnly Cookie 认证、私有响应
`no-store` 和后端 401 会话清理。Portfolio 详情页提供 CSV 文件选择、大小与格式
提示、逐行 preview、汇总、显式 commit 和提交结果；文件变化后必须重新 preview，
commit 后刷新 ledger。前端只做 1,000,000 bytes/CSV 类型的快速校验，后端仍是
500 行、字段、Decimal、所有权、交易规则与幂等性的最终权威。

验收标准：浏览器 token 边界不变；同一原始文件先 preview 后 commit，可清楚显示
`ready`/`replay`/`invalid` 与 `created`/`replayed`/`failed`，并在部分失败时保留逐行
错误；文件变化会使旧 preview 失效，完全重试可辨认 replay。Vitest/Testing Library
覆盖文件校验、状态和错误映射，Playwright 覆盖导入闭环及 375/768/1440px 关键布局；
`pnpm check`、production build、前端 CI 与公开 Vercel 验收通过，README/OpenAPI
类型漂移检查同步更新。

#### [ ] F2.2 Ledger Lens 品牌统一（3–5h）

依赖：F2.1。

工作内容：将前后端所有面向用户、面试官和搜索引擎的产品名称统一为
`Ledger Lens`，包括前端 Brand/SEO、Landing、Open Graph 图、Dashboard 截图、
README、OpenAPI 展示标题、演示/字幕/面试/简历文档和计划标题。代码类型、API
schema、Python/Node 包名、仓库 slug、URL、环境变量、数据库对象与部署资源名保持
不变，避免品牌更新破坏兼容性。

验收标准：文本与图片资产不再展示旧产品名；
`PortfolioAnalytics` 等领域/API 技术标识保持不变；OpenAPI snapshot 与前端生成
类型同步；前后端质量门禁、production build、Playwright、GitHub CI、Vercel 部署
和公开首页 metadata/品牌展示通过。

### Post-V1 范围边界

- 不引入微服务、Kafka、Kubernetes、实时行情、价格预测、自动交易或买卖建议。
- 不在公开前端存储 JWT，不因前端存在而放松后端所有权校验。
- 不为演示伪造市场数据新鲜度、生产容量、云平台 SLA 或未运行的测试结果。

## 9. Backlog

以下内容不进入当前 P0/P1 关键路径；已重新排期的第二 Provider、CSV 导入、
AnalysisSnapshot 查询、限流、前端和轻量公开部署以第 8 节为准：

- 基准指数对比和Beta。
- 资产集中度高级分析。
- 多币种和外汇换算。
- Refresh token与token撤销。
- 生产级高可用部署与监控面板。

只有第 8 节关键路径稳定，且修改本文件明确调整优先级后，才能开始其余 Backlog。

## 10. 进度日志

按时间倒序记录。每条只写事实、验证结果和下一步，不记录未验证的完成声明。

### 2026-07-22

- [x] F2.1 已完成独立前端 CSV 交易导入 UI。固定 OpenAPI snapshot 与生成类型
  已升级到后端 `v1.2.0`；BFF 仅新增精确的 CSV preview/commit allowlist，以
  原始 `text/csv` 字节转发并保留 1 MB 上限、同源写入、HttpOnly Cookie、
  `no-store`、401 清除会话和 60 秒导入 timeout，浏览器仍不接触 JWT。
- Portfolio workspace 已加入下载模板、文件快速校验、preview 汇总与逐行
  `ready`/`replay`/`invalid`、显式 commit、`created`/`replayed`/`failed`、部分失败
  说明和 ledger 刷新；文件变化会使旧 preview 失效，后端继续负责 UTF-8、500 行、
  Decimal、所有权、ledger 规则与幂等性。
- 验证：Node.js 24 的 `pnpm check` 通过 lint、typecheck、55 项 Vitest/Testing
  Library 测试和 OpenAPI 漂移检查；`pnpm build` 通过；`pnpm test:e2e` 的 7 项
  Playwright 测试通过 CSV preview、部分提交、幂等 replay、完整分析闭环及
  375/768/1440px 布局；`pnpm audit --audit-level high` 未发现已知漏洞。前端
  [PR #6](https://github.com/RujingXu-bit/Ledger-Lens-web/pull/6) 已合并到
  `main@d453cb04887c96cc1f6ea9ec449ce201be50d66d`，PR 与合并后 Frontend CI、
  Vercel production deployment 均通过；正式域名 4 项公网验收从新访客注册开始，
  完成真实 CSV preview/commit、ledger、analytics、insight 与历史 snapshot 闭环。

- [x] R2.2 已正式发布后端 `v1.2.0`。发布起始基线为
  `main@2f310b0a49dc010bc960fe249e35c3b94f5095ed`，且
  `HEAD == origin/main: yes`、`Worktree clean: yes`；PR #31 squash merge 后的
  已验证 release commit 为 `58bedea5eb582d4d4275c0778f914cb69bc9abc8`。
  Python 包、`uv.lock`、FastAPI OpenAPI、README、简历入口与 changelog 均同步为
  `1.2.0`，E2.1/E2.2 和长窗口 fail-closed 修复已从 Unreleased 正式发布。
- 发布门禁：`make check` 通过 Ruff、format、严格 mypy（95 个源文件）和 223 项
  单元测试，branch coverage 90%；`make test-all` 通过 239 项单元/集成测试，
  branch coverage 94%；`make db-check`、`uv lock --check`、Compose 配置、
  `git diff --check` 与 `make image-smoke` 均通过。`uv build` 生成 `1.2.0` wheel
  与 sdist，wheel metadata 明确为 `Version: 1.2.0`；真实 yfinance、Twelve Data
  短窗口及 5,000 点长窗口 contract 共 3 项通过。PR #31 的两个 quality jobs 和
  release commit CI run `29951157732` 全部成功。
- annotated `v1.2.0` tag 已推送并解引用到 release commit；非 draft、非
  prerelease GitHub Release 已发布：
  <https://github.com/RujingXu-bit/Ledger-Lens-api/releases/tag/v1.2.0>。
  Release 附带已验证的 wheel 与 sdist，GitHub 分别记录 SHA-256 digest；tag、
  Release 和构建元数据版本一致。计划内 Post-V1/P2 工作至此无剩余任务。

- [x] R2.1 最终复审结论为 **PASS**。Review baseline:
  `main@2cf07bd27e928d30065ebd40aee8541d35397d26`；
  `HEAD == origin/main: yes`；`Worktree clean: yes`。PR #29 已合并唯一 P1 整改，
  Twelve Data 短窗口真实 contract 正常返回，长窗口真实 contract 在 5,000 点
  上限稳定 fail closed；未发现新的 P0、P1、P2 或 P3 问题。
- 最终复审验证：`make check` 通过 Ruff、format、严格 mypy（95 个源文件）和
  223 项单元测试，branch coverage 90%；`make test-all` 最终通过 239 项单元/集成
  测试，branch coverage 94%；首次完整运行仅因 2 秒 Redis 固定窗口测试跨边界而
  观察到 24/30 允许，聚焦重跑和完整重跑均通过，不属于实现回归。`make db-check`
  无迁移漂移，`uv lock --check`、`uv build`、`git diff --check` 和
  `make image-smoke` 通过；真实 Provider contract 3 项通过，DeepSeek 未显式启用
  而按设计跳过。合并提交 GitHub Actions run `29950282879` 成功。R2.1 门禁解除，
  下一步：执行 `R2.2` 发布后端 `v1.2.0`。

- [x] R2.1 的唯一 P1 已完成整改。Twelve Data 请求现在显式设置
  `outputsize=5000`；响应达到 5,000 条时以稳定
  `MarketDataInvalidResponseError` fail closed，不再把可能截断的价格序列交给
  analytics。新增覆盖 26 年请求窗口与 5,000 条截断响应的离线回归测试，以及
  真实长窗口 contract；方法论和架构文档同步说明供应商上限及缩短日期范围要求。
- 整改验证：`make check` 通过 Ruff、format、严格 mypy（95 个源文件）与 223 项
  单元测试，branch coverage 90%；`make test-all` 通过 239 项单元/集成测试，
  branch coverage 94%；`make db-check` 无迁移漂移，`uv lock --check`、`uv build`、
  `git diff --check` 和 `make image-smoke` 通过。使用 Twelve Data 官方 demo key
  执行 `make test-contract`，Twelve Data 短/长窗口与 yfinance 共 3 项通过，
  DeepSeek 因未显式启用按设计跳过。R2.1 主任务保持未勾选；下一步是在整改合并后
  从同步、干净的 `origin/main` 重新记录审查基线并给出最终结论。

- [ ] R2.1 最终审查结论为 **FAIL**。Review baseline:
  `main@1ea3959e5b552d93b0c755caea0a9c031d9060a1`；
  `HEAD == origin/main: yes`；`Worktree clean: yes`。发现 1 个未解决 P1：
  `TwelveDataMarketDataProvider` 未检测 `/time_series` 的 5,000 数据点上限。
  使用官方 demo key 请求 AAPL `2000-01-01` 至 `2026-01-01` 时，实际返回恰好
  5,000 条且最早日期为 `2006-02-16`，适配器仍作为成功结果返回；这会让长周期
  analytics 在未披露的截断序列上计算收益、波动率、回撤和 Sharpe Ratio。
  Twelve Data 官方历史数据说明确认单次请求最多 5,000 条：
  <https://support.twelvedata.com/en/articles/5214728-getting-historical-data>。
- 其余审查证据通过：`make check` 通过 Ruff、format、严格 mypy（95 个源文件）
  与 222 项单元测试，branch coverage 90%；`make test-all` 通过 238 项单元/集成
  测试，branch coverage 94%；`make db-check` 无迁移漂移，`uv lock --check`、
  `uv build`、`git diff --check` 和 `make image-smoke` 通过。真实 contract 使用
  官方 demo key 验证 Twelve Data 与 yfinance 共 2 项通过，DeepSeek 因未显式
  启用而按设计跳过；基线 GitHub Actions run `29948743386` 成功。
- 公网 Render 验收通过 `/health` request ID、OpenAPI 两个 CSV 路径、隔离合成
  用户注册、Portfolio 创建、2 行 preview、commit 与完整 retry；重试返回相同
  PostgreSQL transaction ID。CSV 所有权在解析前校验、预览不写入、逐行提交复用
  原交易锁/Decimal/领域/幂等边界，未发现 P0、P1、P2 或 P3 问题。
- 整改要求：Twelve Data 对超过单次上限的日期范围执行可验证的分段获取并合并，
  或在任何可能截断时返回稳定、明确的错误；新增超过 5,000 个交易日的离线回归
  测试和真实长窗口 contract 证据。整改合并到最新 `origin/main` 后必须重新执行
  R2.1 全部门禁；复审 PASS 前不得创建包含 E2.x 的正式 tag 或 GitHub Release。

- [x] E2.2 已完成 preview-first CSV 交易导入：新增 owner-scoped
  `POST /portfolios/{id}/transactions/import/preview` 与
  `POST /portfolios/{id}/transactions/import`。输入为 bounded UTF-8 `text/csv`，
  支持 BOM/严格 quoting，限制 1,000,000 bytes 与 500 个非空数据行；必填稳定
  `external_id`、交易类型和带时区发生时间，未知/重复/缺失 header 与文件级错误
  返回稳定 `csv_import_invalid`。
- Preview 在解析前验证所有权、不写数据，自上而下模拟现有 ledger 并逐行返回
  `ready`/`replay`/`invalid` 及结构化 field/error。Commit 重新解析并对每个有效行
  调用原 `TransactionService`，因此继续执行 Portfolio lock、Decimal 量化、交易/
  持仓规则、数据库唯一约束和 idempotency comparison；返回
  `created`/`replayed`/`failed`，预期失败不掩盖已成功行。完全重试实测返回相同
  PostgreSQL transaction ID，跨用户 preview/commit 均为与不存在资源一致的 404。
- 验证：`make check` 通过 Ruff、format、严格 mypy、222 项单元测试，branch
  coverage 90%；`make test-all` 通过 238 项单元/集成测试，branch coverage 94%；
  其中 PostgreSQL CSV 持久化/部分失败/完整 replay 与 owner isolation 通过。
  `make db-check` 无迁移漂移，`uv lock --check`、`git diff --check`、OpenAPI 端点/
  schema 检查和 `make image-smoke` 均通过。格式、列、curl 流程、并发与部分提交
  语义记录于 `docs/csv-import.md`；P2 无剩余任务。

- [x] E2.1 已完成第二真实市场数据源：新增 async Twelve Data adapter，显式请求
  `time_series` 的 `1day`/`adjust=all` 数据，将 exchange-local session date 与
  正数有限 Decimal close 归一化为现有 `PriceBar`；领域、应用服务和公开 API 无
  变化。`MARKET_DATA_PROVIDER` 显式选择 `yfinance` 或 `twelve_data`，默认仍为
  无凭据 yfinance；选择 Twelve Data 但缺少 `TWELVE_DATA_API_KEY` 时启动即失败，
  不执行静默 fallback。
- E2.1 复用现有 provider observation、bounded retry/deadline、Redis cache/stale
  语义，以 provider 名称隔离缓存键和日志。新增 21 项 adapter 单元测试、3 项
  factory 测试及同一 `PriceBar` contract 的 Twelve Data opt-in 测试；官方 demo
  key 的真实 AAPL 2025-01-02 至 2025-01-10 contract 实测通过。
- 验证：`make check` 通过 Ruff、format、严格 mypy、204 项单元测试，branch
  coverage 89%；`make test-all` 通过 219 项单元/集成测试，branch coverage 93%；
  `make db-check` 无迁移漂移，`uv lock --check`、`git diff --check` 和生产依赖
  `make image-smoke` 均通过。下一步：从最新 `main` 独立执行 E2.2。

- [x] M1.1 已完成三分钟视频与求职作品包装：新增中文导演提示、逐秒时间轴、
  373 词完整英文口播及逐句一致的 18 条 SRT；最终成片为 3:00、1920×1080、
  16:9、30fps，含 AAC 英文口播和烧录字幕。成片作为 `v1.1.0` Release asset
  发布：
  <https://github.com/RujingXu-bit/Ledger-Lens-api/releases/download/v1.1.0/portfolio-analytics-demo.mp4>。
- 画面覆盖 Landing、注册、Portfolio 创建、DEPOSIT/BUY ledger、Provider-backed
  analytics、四项指标、资产权重、`as_of`/provenance、展开 methodology、确定性
  风险回退、limitations、免责声明、历史 snapshot 和 CI。所有 Provider-backed
  静态片段明确标记为 2026-07-22 预录成功结果；`/demo` 明确标记为不发起 Provider
  请求的 deterministic offline fixture。
- 最终 MP4 连续三次完整解码彩排均通过，并对 11 个时间点完成视觉 QA；首版因
  字幕过大被拒绝，修正后复验。Provider 故障备用讲解已实际切换 `/demo`，验证
  固定指标、allocation、risk summary、ledger 和 snapshot provenance，再切换到
  明确标记的预录成功画面与 CI 证据，不把 fixture、旧缓存或预录素材描述为当前
  Provider 结果。复现命令、SHA-256 和边界记录于
  `docs/demo-video-verification.md`。
- Backend README 首屏新增 Dashboard 截图、Live Demo、三分钟视频、正式 Release、
  CI badge、前端仓库、面试导览和简历条目；frontend README 同步入口与截图。
  两个仓库的 GitHub description、Homepage 和 Topics 已统一，个人 GitHub Website
  指向 Live Demo；`docs/resume-project-entry.md` 提供可直接粘贴且链接一致的英文
  简历项目条目。前端 PR #5 的 quality/browser/Vercel checks 均通过，已 squash
  merge 为 `cea77e252ee76182436bdced52afee3f5a849f09`：
  <https://github.com/RujingXu-bit/Ledger-Lens-web/pull/5>。
- 验证：后端 `make check` 通过 Ruff、format、mypy 和 180 项单元测试，branch
  coverage 89%；前端 `pnpm check` 通过 42 项测试，`pnpm build` 通过 12 个 route；
  Live Demo、offline fixture、前后端仓库、Release、视频和个人主页链接均实测
  HTTP 200。M1.1 后无必须开发项；`E2.1`/`E2.2` 保持可选。

- [x] D1.1 已完成低成本公开部署与公网闭环：Next.js 前端/BFF 运行于
  Vercel，Docker API 运行于 Render Starter Frankfurt，PostgreSQL 使用 Neon
  Frankfurt，Redis 使用 Upstash Ireland；Render pre-deploy 独立执行 Alembic
  migration，`/health` 返回 200 与 `X-Request-ID`。公开环境不配置 DeepSeek key，
  风险摘要稳定使用 `deterministic_rules` 回退。
- 公网新访客验收覆盖 Landing、明确标记的离线 fixture、注册自动登录、Portfolio
  创建、DEPOSIT/BUY ledger、显式 analytics、资产权重与 methodology、风险摘要、
  snapshot 历史及刷新后读取。跨用户资源返回与不存在资源一致的 404；Redis 固定
  窗口实测第 11 次 insights 请求返回 `429 rate_limited` 与 `Retry-After`。Render
  与 Vercel 日志未出现密码、JWT、access token、数据库/Redis URL、请求体或明文
  rate-limit identifier。
- 验证：公网 API
  <https://portfolio-analytics-api-ou9p.onrender.com/health> 与前端
  <https://portfolio-analytics-web-hazel.vercel.app> 可访问；后端 synthetic acceptance
  通过幂等、历史、所有权和 deterministic fallback；前端 `pnpm check` 的 42 项
  Vitest 测试、`pnpm build` 与公网 Playwright 4 项测试通过，覆盖完整真实闭环及
  375/768/1440px 无横向溢出。Landing Lighthouse 实测 Performance 99、
  Accessibility 100、Best Practices 100、SEO 100（单次公网实验数据，不作为
  SLA）。前端 PR #4 的 quality/browser 与 Vercel checks 均通过，已 squash merge
  为 `6f43020d4f148140efe108d6a171bb987cefe95a`：
  <https://github.com/RujingXu-bit/Ledger-Lens-web/pull/4>。迁移、应用回滚、
  秘密配置与限流降级步骤记录于 `docs/deployment.md`。下一步：执行 `M1.1`。

- [x] F1.2 在独立前端仓库完成英文求职展示闭环：Landing 与明确标记为
  deterministic offline fixture 的 `/demo`、注册自动登录、Portfolio 列表与
  创建、条件化交易表单和 ledger、显式日期 analytics、四项指标、资产权重、
  `as_of`/stale provenance/methodology、用户主动生成的风险摘要及 snapshot
  历史；未加入编辑删除、实时行情、预测、自动交易或 refresh token。
- 私有页面继续经 Next.js BFF 访问后端；Playwright 主流程证明 JWT 不出现在
  页面、响应体、Local Storage、Session Storage、客户端日志或可读取 Cookie。
  375/768/1440px 布局无横向溢出，键盘路径通过；浏览器实测 Landing 与 fixture
  页面无 console warning/error，并修正了 fixture provenance 文案。
- 验证：Node 24 下 `pnpm check` 通过 ESLint、TypeScript、14 个 Vitest 文件的
  40 项测试及 OpenAPI 类型漂移检查；`pnpm build` 通过 12 个 Next.js route 的
  production build；`pnpm test:e2e` 的 4 项 Chromium 测试通过完整注册至历史
  查询闭环及三种响应式宽度；`pnpm audit` 为 0 个已知漏洞，`git diff --check`
  通过。GitHub Actions run `29933342504` 的 quality/browser jobs 均通过，PR #2
  已合并为 `a139048461ad60e538c3a92b0e3837ba0f853e37`：
  <https://github.com/RujingXu-bit/Ledger-Lens-web/pull/2>。annotated
  `v1.0.0` tag 与该提交一致，非 draft、非 prerelease Release 已发布：
  <https://github.com/RujingXu-bit/Ledger-Lens-web/releases/tag/v1.0.0>。
  下一步：执行 `D1.1`。

- [x] F1.1 在独立公开仓库
  <https://github.com/RujingXu-bit/Ledger-Lens-web> 建立 Node.js 24、
  Next.js 16.2.11 App Router、TypeScript、pnpm 11.9.0 与 Tailwind 基线；固定后端
  `v1.1.0` OpenAPI snapshot 并生成 TypeScript declarations，CI 会重新生成到临时
  文件并检查类型漂移。
- Next.js Route Handlers 只代理明确 allowlist 内的 auth、Portfolio、Transaction、
  Analytics 与 Insight 路径；access token 只写入 HttpOnly、生产强制 Secure、
  SameSite=Lax 的短期 Cookie。私有响应使用 `no-store`，写请求执行精确同源 Origin
  校验，FastAPI 401 清除 Cookie，客户端请求助手跳转 `/login`；浏览器不直连
  FastAPI，因此未启用 CORS。
- 验证：Node 24 下 `pnpm check` 通过 ESLint、TypeScript、29 项 Vitest 测试和
  OpenAPI 类型漂移检查；`pnpm build` 通过 Next.js production build；
  `pnpm audit` 为 0 个已知漏洞，`git diff --check` 通过。GitHub PR #1 的远端
  `quality` job 通过并合并为
  `5a9266a9af112fb7fe454713d166957d73d44b74`：
  <https://github.com/RujingXu-bit/Ledger-Lens-web/pull/1>。下一步：执行
  `F1.2`。

- [x] E1.2 完成公网请求限流与部署基线：Redis 固定窗口按注册 IP、登录 IP、
  规范化 email、analytics 用户、insights 用户和普通认证用户分别使用
  `5/10min`、`10/10min`、`5/10min`、`20/min`、`10/min`、`120/min` 阈值。
  所有 identifier 经部署 secret 的 HMAC-SHA256 后进入 key；不保存明文 IP、
  email、JWT 或请求体。超限统一返回 `429 rate_limited` 和 `Retry-After`；Redis
  或脚本响应失败仅记录异常类型与 `rate_limit_bypass` 并允许核心请求继续。
- 新增 Render Starter Docker Blueprint、独立 pre-deploy Alembic migration、
  `/health` 检查及 Neon/Upstash TLS、秘密、回滚和公网验收说明；Render 是唯一
  默认信任 forwarded IP 的环境。公开配置不设置 `DEEPSEEK_API_KEY`，继续使用
  deterministic fallback；实际云资源创建与公网闭环仍属于 D1.1。
- 验证：`make check` 通过 Ruff、format、严格 mypy（85 个源文件）和 177 项
  离线单元测试，branch coverage 89%；`make test-all` 的 192 项单元/集成测试
  全部通过，综合 branch coverage 93%，其中真实 Redis 并发边界为 30 次同时
  请求严格 20 通过/10 拒绝且 key 自动过期。`make image-smoke`、`uv build`、
  `uv lock --check`、`make db-check`、Compose/Render YAML 与 `git diff --check`
  通过；wheel/sdist 元数据为 `1.1.0`、Python `>=3.12`。
- GitHub PR #18 的两个 quality jobs 和 main 合并提交 CI run `29928214096` 均
  通过。annotated `v1.1.0` tag 与 `origin/main` 同指
  `3f321b6b762f77e52d6773792f43802fffd62ff1`，非 draft、非 prerelease Release
  已发布：<https://github.com/RujingXu-bit/Ledger-Lens-api/releases/tag/v1.1.0>。
  下一步：执行 `F1.1`。

- [x] E1.1 完成前端依赖的查询能力：新增认证后的 `GET /portfolios` 与
  `GET /portfolios/{id}/insights`，统一返回 `items/total/limit/offset`；limit
  默认 20、最大 100。PostgreSQL Portfolio 按 `created_at/id` 倒序，snapshot
  按 `generated_at/id` 倒序；应用服务先执行所有权校验，外部用户和不存在资源
  继续使用相同 `portfolio_not_found` 404。
- snapshot API 结构化返回现有指标、methodology、summary、generator、model、
  prompt version 与生成时间；初始 schema 中可空的 RC narrative/provenance 字段
  保持可读并输出 `null`，没有新增 migration。OpenAPI、README、架构说明与决策
  记录已同步。
- 验证：`make check` 通过 Ruff、format、严格 mypy（80 个源文件）和 164 项
  离线单元测试，branch coverage 为 89%；`make test-all` 的 178 项单元/集成
  测试全部通过，综合 branch coverage 为 93%，覆盖分页排序、总数、跨用户隔离、
  PostgreSQL 持久化和旧 RC snapshot；`uv lock --check`、`make db-check` 与
  `git diff --check` 通过。下一步：执行 `E1.2`。

- [x] R1.2 发布后端正式版 `v1.0.0`。起始发布基线为
  `main@9315cf9920483383fdc3e80e39dbe84412e15042`，且
  `HEAD == origin/main: yes`、`Worktree clean: yes`；正式 release commit 为
  `81cf853e602e4b30c8031c44fdb3564220399f49`。包版本、锁文件、README、
  changelog 和演示措辞已从候选状态更新为正式 V1，未改变运行时 API 或金融
  methodology。
- 发布门禁：`make check` 通过 Ruff、format、严格 mypy（80 个源文件）和
  158 项离线单元测试，branch coverage 为 89%；`make test-all` 的 170 项
  单元/集成测试通过，branch coverage 为 93%；`make image-smoke` 通过非 root
  健康/request-ID 冒烟；`uv build` 生成 `1.0.0` wheel 与 sdist，元数据确认
  Python `>=3.12`；`uv lock --check`、Compose 配置与 `git diff --check` 通过。
  GitHub PR #15 的两个 quality jobs 均通过。
- annotated `v1.0.0` tag 已推送，非 prerelease GitHub Release 已发布：
  <https://github.com/RujingXu-bit/Ledger-Lens-api/releases/tag/v1.0.0>。
  已用 `git branch --merged origin/main` 解析目标并删除 11 个已合并本地功能分支；
  `main`、当前 release 分支、未合并分支和版本 tags 均保留。下一步：执行
  `E1.1`。

- [x] R1.1 建立 Post-V1 路线图：将正式后端发布、前端所需查询、Redis 限流、
  独立 Next.js BFF、完整演示 UI、低成本部署、视频包装、第二 Provider 与 CSV
  导入拆为有依赖和验收标准的独立 Task ID；明确后端 `v1.0.0`/`v1.1.0` 与前端
  `v1.0.0` 的版本边界，并继续排除微服务、预测和自动交易。验证：任务依赖和
  Backlog 交叉检查通过，`git diff --check` 通过。下一步：执行 `R1.2`。

- [x] W5.R Week 5 里程碑审查通过。Review baseline：
  `main@f84e1aad4becbe063591e101575b7b728b68376c`；`HEAD == origin/main: yes`；
  `Worktree clean: yes`。逐项复核 W5.1–W5.5 后未发现 P0、P1、P2 或 P3
  问题，结论为 PASS。
- 验证：`make check` 与 `make test-cov` 均通过 Ruff、format、严格 mypy（80 个
  源文件）和 158 项离线单元测试，branch coverage 为 89%；基线提交对应的
  GitHub Actions CI run `29920997467` 成功完成锁定安装、Ruff/format、mypy、
  离线单元测试、空库 migration/check、12 项 PostgreSQL/Redis 集成测试及非
  root 运行镜像冒烟。金融计算由可人工复核 fixture 覆盖空数据、单点、零波动、
  持续下跌、缺失日期、重复日期、多资产、现金流、费用和无前视估值；领域层未
  导入 FastAPI、SQLAlchemy、Pandas、基础设施或具体 Provider。普通测试使用
  Fake/Mock/ASGI transport，真实 yfinance 与 DeepSeek 调用仅在显式 contract
  开关下运行。`v1.0.0-rc.1` annotated tag、`uv lock --check` 与
  `git diff --check` 均核验通过。

- [x] W5.5 完成 `v1.0.0-rc.1` 候选版本与演示准备：项目包版本更新为
  `1.0.0rc1` 并同步 `uv.lock`，新增候选 changelog、API 驱动演示命令、三分钟
  讲稿及架构/金融口径面试问答。演示只通过公开 endpoint 创建唯一用户、
  Portfolio、DEPOSIT 与 BUY，验证相同 BUY 的幂等 replay 后获取 analytics 和
  insight；不手工修改数据库、不打临时补丁，也不输出密码或 JWT。
- 候选干净环境从无 `.venv`、无 `.env` 的临时副本执行 `uv sync --locked`；
  独立 Compose project 使用全新开发/测试 PostgreSQL 与 Redis、独立端口和
  测试卷。开发空库 `alembic upgrade head`/`check` 通过，随后 `make check` 与
  `make test-all` 全部通过。真实应用启动后，AAPL 2026-01-02 至 2026-01-30
  的演示成功返回四项指标、`stale=false`、同 ID 幂等 replay 和
  `deterministic_rules` insight；无需 DeepSeek 凭据。所有临时容器、网络、
  卷与目录均已清理。
- 最终候选门禁：`make check` 通过 Ruff、format、严格 mypy（80 个源文件）
  和 158 项离线单元测试，综合覆盖率 89%；`make test-all` 的 170 项单元与
  集成测试通过，综合覆盖率 93%；`make image-smoke` 成功构建仅含 production
  依赖、以 UID `10001` 运行的镜像并通过 health/request-ID 冒烟。`uv build`
  成功生成 `portfolio_analytics_api-1.0.0rc1` sdist 与 wheel，元数据确认
  `Version: 1.0.0rc1`、`Requires-Python: >=3.12`；`uv lock --check`、
  `docker compose config --quiet` 与 `git diff --check` 通过。
- 项目级完成定义逐项复核通过：核心持久化流程、空库 migration、Fake/真实
  Provider、四项指标及 methodology、Redis/retry/stale、JWT/所有权、LLM
  确定性回退、离线 CI、容器/README/演示干净环境和可复现实测指标均有当前
  测试或运行证据。已知限制继续在 README 与 changelog 明示；本次只创建本地
  候选分支、提交与 annotated tag，不 push、不建 PR、不对外发布。

- [x] W5.4 完成 README 与交付文档：README 现包含锁定安装、完整环境变量、
  基础设施/空库 migration/启动、运行镜像、认证与所有 9 个已实现 endpoint
  示例、统一错误和 `X-Request-ID`、金融 methodology、缓存/retry/stale、LLM
  回退、安全边界、测试/CI/负载命令，以及 W5.2 的原始实测环境和数字。文档
  明确未实现 portfolio 列表、insight 历史、第二 Provider、前端、生产部署或
  已发布 V1，未扩大当前范围。
- `docs/architecture.md`、`docs/decisions.md` 与 `docs/performance.md` 已统一
  request/logging 路径、离线 CI、非 root production-only 镜像、独立 migration、
  降级策略及本机合成上游性能边界。临时目录中的干净副本确认初始无 `.venv`
  和 `.env`，随后用锁文件安装，在独立 Compose project/端口上从空 `_test`
  数据库 migration/check，启动 API，并通过 health 200、注册 201、登录 200 与
  UUID request ID 冒烟；本次临时容器、网络、测试卷和目录均已清理。
- 最终验证：`make check` 通过 Ruff、format、严格 mypy（78 个源文件）和
  156 项离线单元测试，综合覆盖率 89%；`make test-all` 的 168 项单元与集成
  测试通过，综合覆盖率 93%；`make image-smoke` 成功构建只含 production
  依赖、以 UID `10001` 运行的镜像并通过容器健康冒烟；`uv lock --check`、
  `docker compose config --quiet` 与 `git diff --check` 通过。W5.2 后未改动
  运行时或 benchmark 路径，因此按计划未重复负载实测。下一步仅为尚未执行的
  `W5.5`。

- [x] W5.3 完善离线 CI 与运行镜像：GitHub Actions 使用固定 uv 版本和锁文件，
  启动临时 PostgreSQL 16/Redis 7 后依次执行 Ruff、format、严格 mypy、离线
  单元测试、空 `_test` 库 Alembic upgrade/check、集成测试及镜像构建/健康
  冒烟；CI 仅使用无秘密测试配置，不运行 yfinance/DeepSeek contract tests。
- 新增 Python 3.12 slim 运行镜像与 `.dockerignore`；镜像仅安装 production
  依赖、包含 migration，并以非 root UID `10001` 运行。`make image-smoke`
  成功构建镜像，核验非 root 用户并在随机 loopback 端口启动临时容器，`/health`
  与 `X-Request-ID` 冒烟通过。migration 仍是独立部署步骤，不在应用启动时隐式
  执行。
- 本机以 CI 同等无秘密环境验证：空 `_test` schema 从零升级到 head，
  `alembic check` 无漂移，12 项 PostgreSQL/Redis 集成测试通过；
  `docker compose config --quiet` 通过；`make check` 通过 Ruff、format、mypy
  （78 个源文件）和 156 项离线单元测试，综合覆盖率 89%；`make test-all` 的
  168 项单元与集成测试通过，综合覆盖率 93%；`uv lock --check` 与
  `git diff --check` 通过。下一步：执行 `W5.4`。

- [x] W5.2 完成可复现 Locust 冷/热缓存负载测试：单进程 Uvicorn 使用真实
  FastAPI、认证、PostgreSQL Repository、Redis cache 与 analytics 路径，仅将
  yfinance 替换为固定 50ms 延迟的确定性 Provider；fixture 为 1 个用户、1 个
  Portfolio、1 笔 BUY、1 个 symbol 和 2,000 个价格点。测试使用隔离 `_test`
  数据库与唯一 Redis namespace，不访问真实 Provider 或 LLM。
- 正式实测环境为 macOS 26.5.2 arm64、Python 3.12.13、Locust 2.46.1、
  PostgreSQL 16、Redis 7、10 用户以 2 用户/秒生成、每场景 60 秒。冷缓存使用
  唯一 60–252 日区间：7,448 请求，P50 66ms、P95 120ms、124.343 req/s、
  0 错误、0% cache hit；日志核对 7,448 miss/Provider calls，Provider P50/P95
  为 51.000/52.023ms。热缓存使用预热 252 日区间：25,020 请求，P50 22ms、
  P95 34ms、417.561 req/s、0 错误、100% cache hit，测量区间无 Provider 调用。
- `docs/performance.md` 明确这些数字是本机、单 worker、合成上游的缓存路径对比，
  不是生产容量证明。验证：4 项 benchmark 单元测试通过；`make load-test` 从空
  测试库 migration 后完成两场景并交叉校验 Locust/JSON 日志；`make check`
  通过 Ruff、format、mypy（75 个源文件）和 150 项离线单元测试，综合覆盖率
  89%；`make test-all` 的 162 项单元与集成测试通过，综合覆盖率 93%；
  `uv lock --check` 与 `git diff --check` 通过。下一步：执行 `W5.3`。

- [x] W5.1 完成可观测性和安全检查：所有 HTTP 请求使用 UUID request ID，
  合法 `X-Request-ID` 会规范化并贯穿响应，缺失或非法值由服务端替换；异步
  request context 将 HTTP、cache、Provider 和 insight 回退事件关联到同一 ID。
  应用与 Uvicorn 统一输出 UTC 单行 JSON，仅序列化固定白名单字段，不记录
  request body、query、Authorization、配置、缓存 payload 或异常原文。
- 市场数据 Provider 在 retry 边界内记录每次真实调用的 latency、outcome 和
  稳定错误类别；market-data/insight cache 使用可统计的 hit、miss、stale、
  bypass、corrupt 事件。未处理异常返回通用 500，重复邮箱响应不再回显邮箱。
  12 项聚焦测试覆盖并发 request ID 隔离、非法 ID、JSON schema、全部 Provider
  错误类别，以及密码、JWT、API Key 和异常内容哨兵不泄漏。
- 验证：`make check` 通过 Ruff、format、mypy（68 个源文件）和 146 项离线
  单元测试，综合覆盖率 89%；隔离 PostgreSQL/Redis 上 `make test-all` 的 158
  项单元与集成测试全部通过，综合覆盖率 93%；`uv lock --check` 和
  `git diff --check` 通过。下一步：执行 `W5.2 负载测试与实测指标`。

- [x] W4.R Week 4 里程碑审查通过。Review baseline：
  `main@e0032f441588f928b004ed308b7fea599339d27d`；`HEAD == origin/main: yes`；
  `Worktree clean: yes`。逐项复核 W4.1–W4.4 后未发现 P0、P1、P2 或 P3
  问题，结论为 PASS。
- 验证：`make check` 与 `make test-cov` 均通过 Ruff、format、mypy 和 134 项
  离线单元测试，branch coverage 为 88%；隔离 PostgreSQL/Redis 启动后，
  `make test-all` 的 146 项单元与集成测试全部通过，综合 branch coverage 为
  93%。首次 `make test-all` 因测试服务未启动失败，服务就绪后的重跑通过；
  该环境前置失败不计为实现缺陷。领域层未导入 FastAPI、SQLAlchemy、Pandas、
  yfinance 或具体 Provider；真实 yfinance 与 DeepSeek contract 测试均保持显式
  opt-in，默认测试未发现真实外网访问。W4.R 已通过，W5 门禁解除；下一步：
  执行 `W5.1`。

- [x] W4.4 完成单一 DeepSeek LLM Provider：应用层新增 `InsightGenerator`
  协议，Provider 只接收后端已计算的结构化指标、资产权重、`as_of`、stale
  状态和 methodology；响应使用严格 JSON schema 校验，风险等级、风险因素、
  核心限制和非投资建议声明继续由 `risk-rules-v1` 决定，LLM 不参与金融计算。
- DeepSeek 调用使用明确超时且不在 SDK 内重试；限额、超时、HTTP、解析或内容
  安全校验失败均回退确定性摘要，不影响 analytics。成功响应按完整输入、Provider、
  模型与提示词版本缓存；每次实际 insight 结果持久化 AnalysisSnapshot，记录模型、
  提示词版本、生成时间及无秘密的结构化输入摘要。未配置 `DEEPSEEK_API_KEY` 时
  应用保持纯确定性运行，不把可选外部凭据变成核心可用性依赖。
- 验证：38 项聚焦 insight/缓存/DeepSeek mock/API 离线测试通过；`make test-all`
  的 146 项单元与 PostgreSQL/Redis 集成测试全部通过，综合 branch coverage 为
  93%，覆盖 LLM 超时回退、缓存、跨用户 insight 隔离和 AnalysisSnapshot
  持久化；`make check`、`uv lock --check` 与 `git diff --check` 通过。真实
  DeepSeek contract 测试保持显式 opt-in，并使用本地忽略的 `.env` 凭据完成
  1 项真实请求验证；密钥未进入 Git 跟踪范围。下一步：执行 `W5.1`。

- [x] W4.3 完成确定性风险摘要：新增纯领域 `risk-rules-v1`，按固定顺序
  解释年化波动率、最大回撤、历史 Sharpe Ratio 和最新单一证券集中度，并用
  公开阈值输出 low、moderate、high 或 insufficient_data。缺失统计、历史
  adjusted-close/年化/无风险利率假设、集中度能力边界和 stale 数据均进入明确
  limitations；风险等级不依赖 LLM、网络、随机数或系统当前时间。
- 新增受认证和所有权保护的 `POST /portfolios/{id}/insights`，固定返回信息用途/
  非投资建议声明，不生成买入、卖出或保证收益措辞。验证：27 项聚焦规则与 API
  离线测试通过；`make check` 通过 Ruff、format、mypy（57 个源文件）及 123 项
  离线单元测试，综合 branch coverage 为 88%；`uv lock --check` 与
  `git diff --check` 通过。下一步：执行 `W4.4 接入一个LLM Provider`。

- [x] W4.2 完成资源所有权：所有现有 `/portfolios` 路径统一要求 Bearer
  token；创建 portfolio 时绑定当前用户，应用服务在 portfolio 查询、交易写入
  与列表、analytics 数据加载前均校验 `owner_id`。不存在与属于其他用户的
  portfolio 统一返回 `portfolio_not_found` 404，避免直接 ID 猜测泄漏资源存在性。
- 新增 Alembic revision 将 `portfolios.owner_id` 设为非空；若历史库仍有无主
  portfolio，迁移保留数据并明确失败，不删除记录或伪造归属。验证：29 项聚焦
  ownership/交易/内存测试通过；`make check` 通过 Ruff、format、mypy（55 个
  源文件）及 118 项离线单元测试，综合 branch coverage 为 88%；完整
  PostgreSQL/Redis 集成测试的 11 项唯一路径均通过，其中跨用户读取/修改直接
  ID、空库 migration 和无主数据迁移拒绝均已覆盖；`uv lock --check` 与
  `git diff --check` 通过。下一步：执行 `W4.3 实现确定性风险摘要`。

- [x] W4.1 完成用户认证：新增小写规范化邮箱注册与唯一性处理，密码通过
  Argon2 在线程池中哈希/校验且只持久化哈希；`POST /auth/register` 与
  `POST /auth/login` 返回统一 schema。JWT access token 使用固定 HS256
  算法，强制校验 subject、签发/过期时间、issuer、audience 和 token 类型；
  签名密钥只从环境读取，错误凭据、未知用户、畸形或过期 token 使用同一
  401 认证错误，未引入 V1 外的 refresh token 或撤销机制。
- 验证：`make check` 通过 Ruff、format、mypy（55 个源文件）及 116 项离线
  单元测试，综合 branch coverage 为 88%；注册、成功登录、错误密码/未知邮箱、
  重复邮箱与过期 token 聚焦测试 6 项通过；PostgreSQL 用户持久化/唯一性与
  空库 migration 聚焦集成测试 2 项通过；`uv lock --check` 和
  `git diff --check` 通过。下一步：执行 `W4.2 实现资源所有权`。

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
