# Crypto Arbitrage Monitor

Real-time cryptocurrency price spread monitoring across 5 exchanges (Bithumb, Upbit, Binance, Bybit, Coinone) with Telegram alert delivery when user-defined thresholds are exceeded.

## Overview

- **Input**: Real-time market data from 5 exchange APIs (Bithumb, Upbit, Binance, Bybit, Coinone)
- **Output**: Full-stack web application — backend (API server, exchange connectors, spread engine, Telegram bot) + frontend (PC web dashboard)
- **Frequency**: On-demand (one-time development workflow)
- **Autopilot**: disabled
- **pACS**: enabled

---

## Inherited DNA (Parent Genome)

> This workflow inherits the complete genome of AgenticWorkflow.
> Purpose varies by domain; the genome is identical. See `soul.md §0`.

**Constitutional Principles** (adapted to this workflow's domain):

1. **Quality Absolutism** — Every architectural decision, code module, and integration point is evaluated solely by its contribution to a production-quality, reliable real-time monitoring system. Speed of development and token cost are irrelevant.
2. **Single-File SOT** — `.claude/state.yaml` holds all shared workflow state. Only the Orchestrator (or Team Lead during `(team)` steps) writes to SOT. All agents read SOT as read-only and produce output files.
3. **Code Change Protocol** — All code changes follow Intent → Ripple Effect Analysis → Change Plan. Coding Anchor Points (CAP-1: think before coding, CAP-2: simplicity first, CAP-3: goal-based execution, CAP-4: surgical changes) are internalized.

**Inherited Patterns**:

| DNA Component | Inherited Form |
|--------------|---------------|
| 3-Phase Structure | Research → Planning → Implementation |
| SOT Pattern | `.claude/state.yaml` — single writer (Orchestrator/Team Lead) |
| 4-Layer QA | L0 Anti-Skip → L1 Verification → L1.5 pACS → L2 Adversarial Review |
| P1 Hallucination Prevention | Deterministic validation scripts (`validate_*.py`) |
| P2 Expert Delegation | Specialized sub-agents: `@api-researcher`, `@tech-researcher`, `@architect`, `@backend-dev`, `@frontend-dev`, `@integrator` |
| Safety Hooks | `block_destructive_commands.py` — dangerous command blocking |
| Adversarial Review | `@reviewer` for code/architecture + `@fact-checker` for API research accuracy |
| Decision Log | `autopilot-logs/` — transparent decision tracking |
| Context Preservation | Snapshot + Knowledge Archive + RLM restoration |
| Cross-Step Traceability | `[trace:step-N:section-id]` markers in planning and implementation outputs |

**Domain-Specific Gene Expression**:
- **P1 (Data Refinement)** strongly expressed — exchange API responses are noisy (varying formats, inconsistent field names); Python preprocessing normalizes data before agent analysis.
- **P2 (Expert Delegation)** strongly expressed — exchange API research, architecture design, backend development, and frontend development each require deep specialized expertise.
- **CCP (Code Change Protocol)** strongly expressed — full-stack development with interconnected backend/frontend requires rigorous ripple effect analysis.
- **Cross-Step Traceability** expressed in Planning→Implementation — architecture decisions must be traceable from design docs to actual code structure.

---

## Research

### 1. Exchange API Research
- **Pre-processing**: none (primary research — no existing data to filter)
- **Agent**: `@api-researcher` (sonnet)
- **Verification**:
  - [ ] All 5 exchanges documented: Bithumb, Upbit, Binance, Bybit, Coinone
  - [ ] Each exchange entry includes: REST API endpoints (ticker, orderbook), WebSocket streaming endpoints, authentication method, rate limits, response data format with example
  - [ ] KRW-quoted pairs (domestic: Bithumb, Upbit, Coinone) vs USDT-quoted pairs (international: Binance, Bybit) currency distinction documented
  - [ ] Kimchi premium calculation method documented (KRW price vs USD/USDT price × exchange rate)
  - [ ] Known API limitations, downtime patterns, and error handling requirements per exchange
- **Task**: Research and document all 5 exchange APIs for real-time price data collection. Focus on: (1) REST endpoints for initial price snapshot, (2) WebSocket endpoints for real-time streaming, (3) authentication and API key requirements, (4) rate limits and throttling policies, (5) data format differences between domestic (KRW) and international (USDT) exchanges, (6) kimchi premium calculation methodology.
- **Output**: `research/exchange-api-analysis.md`
- **Review**: `@fact-checker` — API endpoints, rate limits, and authentication methods must be factually accurate
- **Translation**: `@translator` → `research/exchange-api-analysis.ko.md`
- **Post-processing**: Extract a structured summary table (exchange × feature matrix) as `research/exchange-matrix.md` for Step 4 consumption

### 2. Tech Stack & Architecture Research
- **Pre-processing**: none (primary research)
- **Agent**: `@tech-researcher` (sonnet)
- **Verification**:
  - [ ] Backend framework comparison: ≥ 3 options evaluated with pros/cons for WebSocket handling and async performance
  - [ ] Frontend framework comparison: ≥ 3 options evaluated with pros/cons for real-time data display
  - [ ] Database recommendation for time-series price data with justification
  - [ ] Telegram Bot API integration approach documented (polling vs webhook, library recommendation)
  - [ ] Currency exchange rate API for KRW/USD conversion identified
  - [ ] At least 2 existing kimchi premium / crypto arbitrage monitors analyzed for reference patterns (source: public repositories or services)
- **Task**: Research and recommend optimal tech stack for the crypto arbitrage monitor. Evaluate: (1) backend frameworks for high-frequency WebSocket connections to 5 exchanges simultaneously, (2) frontend frameworks for real-time dashboard with live price updates, (3) database for storing price history and spread data, (4) Telegram bot integration, (5) KRW/USD exchange rate data source, (6) existing similar projects for architectural reference.
- **Output**: `research/tech-stack-analysis.md`
- **Review**: `@fact-checker` — framework capabilities and performance claims must be verified
- **Translation**: `@translator` → `research/tech-stack-analysis.ko.md`
- **Post-processing**: Generate a decision matrix summary as `research/tech-decision-matrix.md` for human review in Step 3

### 3. (human) Tech Stack Selection
- **Action**: Review the tech stack analysis and decision matrix. Select the preferred tech stack for backend, frontend, database, and supporting tools. Provide any additional requirements or constraints.
- **Command**: `/select-tech-stack`

---

## Planning

### 4. System Architecture Design
- **Pre-processing**: Merge Step 1 exchange API matrix + Step 3 tech stack selection into `temp/architecture-input.md`
- **Agent**: `@architect` (opus)
- **Verification**:
  - [ ] Component diagram covers all major modules: Exchange Connectors (5), WebSocket Manager, Spread Calculator, Alert Engine, Telegram Bot, REST API Server, Frontend App, Database
  - [ ] Data flow documented end-to-end: Exchange API → Data Collection → Normalization → Spread Calculation → Storage + Alert Check → Telegram/Dashboard
  - [ ] WebSocket connection management strategy defined: connection pooling, reconnection logic, heartbeat handling for 5 simultaneous exchange connections
  - [ ] Spread calculation algorithm specified: formula for domestic-to-international spread including KRW/USD conversion, update frequency, spread history retention
  - [ ] Alert trigger mechanism defined: threshold comparison, debounce/cooldown logic, notification batching strategy
  - [ ] Error handling architecture: exchange disconnection recovery, API rate limit handling, partial data scenarios
  - [ ] Pipeline connection: All exchange-specific constraints from Step 1 research are addressed in the architecture (source: Step 1)
  - [ ] Cross-step traceability: ≥ 3 `[trace:step-1:*]` markers linking architecture decisions to API research findings
- **Task**: Design the complete system architecture for the crypto arbitrage monitor. Produce: (1) high-level component diagram (Mermaid), (2) detailed data flow from exchange APIs to user-facing alerts, (3) WebSocket connection management strategy for 5 concurrent exchange connections, (4) spread calculation algorithm with KRW/USD conversion, (5) alert trigger and notification architecture, (6) deployment architecture (containerization, environment config), (7) error recovery and resilience patterns.
- **Output**: `planning/system-architecture.md`
- **Review**: `@reviewer` — architectural completeness and consistency
- **Translation**: `@translator` → `planning/system-architecture.ko.md`
- **Post-processing**: `python3 .claude/hooks/scripts/validate_traceability.py --step 4 --project-dir .`

### 5. API & Data Model Design
- **Pre-processing**: Extract component interfaces from Step 4 architecture as input constraints
- **Agent**: `@architect` (opus)
- **Verification**:
  - [ ] REST API endpoints fully specified: CRUD for alert settings, historical spread data queries, exchange status, user preferences — each with request/response schema
  - [ ] WebSocket event protocol defined: real-time price updates, spread change events, alert notifications — with message format and subscription mechanism
  - [ ] Database schema covers: exchanges, trading_pairs, price_snapshots, spread_records, alert_configs, alert_history, users — with relationships and indexes
  - [ ] Shared TypeScript/Python type definitions for all data entities
  - [ ] Pipeline connection: REST endpoints and WS events map 1:1 to architecture components from Step 4 (source: Step 4)
  - [ ] Cross-step traceability: ≥ 3 `[trace:step-4:*]` markers linking API design to architecture decisions
- **Task**: Design detailed API specifications and data models. Produce: (1) REST API endpoint documentation (OpenAPI-style), (2) WebSocket event protocol specification, (3) database schema with entity-relationship diagram (Mermaid), (4) shared type definitions (TypeScript interfaces or Python dataclasses), (5) data validation rules for user inputs (alert thresholds, trading pair selection).
- **Output**: `planning/api-design.md`
- **Review**: `@reviewer` — API design completeness and consistency with architecture
- **Translation**: `@translator` → `planning/api-design.ko.md`
- **Post-processing**: `python3 .claude/hooks/scripts/validate_traceability.py --step 5 --project-dir .`

### 6. (human) Architecture & Design Review
- **Action**: Review the system architecture and API design. Verify the component structure, data flow, API endpoints, and database schema meet requirements. Provide feedback or approve to proceed to implementation.
- **Command**: `/review-architecture`

---

## Implementation

### 7. Project Scaffolding & Core Infrastructure
- **Pre-processing**: Extract tech stack choices from Step 3 + type definitions from Step 5
- **Agent**: `@scaffolder` (sonnet)
- **Verification**:
  - [ ] Project structure follows the architecture from Step 4: separate backend and frontend directories with shared types
  - [ ] Backend project initializes and builds without errors (chosen framework + dependencies)
  - [ ] Frontend project initializes and builds without errors (chosen framework + dependencies)
  - [ ] Database schema migration files created and applicable
  - [ ] Shared type definitions (from Step 5) integrated into both backend and frontend
  - [ ] Environment configuration template (`.env.example`) with all required variables: exchange API keys, Telegram bot token, database URL, KRW/USD API key
  - [ ] Linting and formatting configured (ESLint/Prettier or equivalent)
  - [ ] Pipeline connection: Project structure matches component diagram from Step 4 (source: Step 4), type definitions match Step 5 schemas (source: Step 5)
- **Task**: Initialize the project with the selected tech stack. Create: (1) monorepo or project structure per architecture, (2) backend project with framework boilerplate and dependencies, (3) frontend project with framework boilerplate and dependencies, (4) shared type definitions package/module, (5) database migration files from Step 5 schema, (6) environment configuration template, (7) linting/formatting config, (8) basic README with setup instructions.
- **Output**: Source code at project root (`src/` or equivalent)
- **Review**: `@reviewer` — project structure and configuration quality
- **Translation**: none (code)
- **Post-processing**: Run build verification: `npm run build` or equivalent to confirm zero errors

### 8. (team) Backend & Frontend Parallel Development
- **Team**: `dev-pipeline`
- **Checkpoint Pattern**: dense — both tasks exceed 10 turns, high rework cost on direction errors
- **Tasks**:
  - `@backend-dev` (opus): Implement all backend services
    - **Checkpoints** (Dense Checkpoint Pattern):
      - CP-1 (Discovery): Confirm exchange connector approach for each of 5 exchanges, WebSocket client library selection, project module structure. Report: list of exchange-specific implementation notes + module dependency graph.
      - CP-2 (Core Services): Exchange connectors (5) + spread calculation engine + database integration working. Report: test results for each exchange connection + sample spread calculations.
      - CP-3 (Complete): Telegram bot integration + REST API server + alert engine + error recovery. Report: full backend test results + pACS self-rating.
    - Deliverables: Exchange API connectors (Bithumb, Upbit, Binance, Bybit, Coinone), WebSocket connection manager with reconnection logic, spread calculation engine (domestic vs international with KRW/USD conversion), Telegram bot service (alert delivery, /start /settings commands), REST API server (alert CRUD, price history, exchange status), alert management service (threshold checking, cooldown, batching)
  - `@frontend-dev` (opus): Implement all frontend components
    - **Checkpoints** (Dense Checkpoint Pattern):
      - CP-1 (Discovery): Confirm component architecture, routing structure, state management approach, WebSocket client setup. Report: component tree + page routing plan.
      - CP-2 (Core Views): Dashboard layout + real-time price display + WebSocket integration working. Report: screenshot-ready component descriptions + data flow verification.
      - CP-3 (Complete): Alert settings UI + Telegram setup + responsive layout + error states. Report: full feature checklist + pACS self-rating.
    - Deliverables: Dashboard layout with exchange price cards, real-time price display with WebSocket updates, spread monitoring view (cross-exchange comparison matrix), alert configuration UI (threshold %, trading pair selection, enable/disable), Telegram connection setup page, responsive PC web design, loading/error/empty states
- **Join**: Team Lead validates both backend and frontend deliverables against Step 4 architecture and Step 5 API design, then proceeds to integration
- **SOT**: Team Lead only writes `state.yaml`. Teammates produce output files only.
- **Verification**:
  - [ ] Backend: All 5 exchange connectors implemented and tested with mock/live data
  - [ ] Backend: Spread calculation produces correct results for sample KRW-USDT pairs
  - [ ] Backend: Telegram bot sends test alert successfully
  - [ ] Backend: REST API serves all endpoints defined in Step 5
  - [ ] Frontend: Dashboard displays real-time prices from WebSocket
  - [ ] Frontend: Alert settings CRUD works through REST API
  - [ ] Frontend: Responsive PC web layout without visual defects
  - [ ] Both: Code follows linting rules from Step 7 scaffolding
  - [ ] Pipeline connection: Implementation matches API contracts from Step 5 (source: Step 5)
- **Review**: `@reviewer` — code quality, error handling, architecture adherence
- **Translation**: none (code)

### 9. Integration Testing & Final Assembly
- **Pre-processing**: Verify backend and frontend build independently before integration
- **Agent**: `@integrator` (opus)
- **Verification**:
  - [ ] Frontend successfully connects to backend WebSocket and displays real-time price data
  - [ ] Full alert flow works end-to-end: price threshold exceeded → spread detected → Telegram message delivered
  - [ ] All 5 exchange connections established simultaneously without conflicts
  - [ ] Spread calculations verified against manual calculation for ≥ 3 trading pairs
  - [ ] Error recovery tested: exchange disconnect → reconnection → data resumption
  - [ ] API rate limits respected under normal operation for all 5 exchanges
  - [ ] Application starts from clean state with documented setup steps
  - [ ] README includes: prerequisites, installation, configuration, running, and usage guide
  - [ ] Cross-step traceability: ≥ 3 `[trace:step-4:*]` or `[trace:step-5:*]` markers linking test scenarios to architecture/design decisions
- **Task**: Integrate backend and frontend, perform end-to-end testing, and prepare for deployment. Execute: (1) wire frontend WebSocket client to backend server, (2) test all 5 exchange connections with real API endpoints, (3) verify spread calculation accuracy with live data, (4) test complete Telegram alert flow, (5) error recovery and resilience testing, (6) performance verification (WebSocket update latency, concurrent connections), (7) write comprehensive README with setup and usage instructions, (8) create .env.example with all required configuration variables documented.
- **Output**: Complete integrated source code + `README.md`
- **Review**: `@reviewer` — integration quality, test coverage, documentation completeness
- **Translation**: `@translator` → `README.ko.md` (README only — code remains English)
- **Post-processing**: `python3 .claude/hooks/scripts/validate_traceability.py --step 9 --project-dir .`

---

## Claude Code Configuration

### Sub-agents

```yaml
# .claude/agents/api-researcher.md
---
name: api-researcher
description: "Cryptocurrency exchange API research specialist. Investigates REST/WebSocket endpoints, authentication, rate limits, and data formats."
model: sonnet
tools: Read, Write, Glob, Grep, WebSearch, WebFetch
maxTurns: 30
memory: project
---

# .claude/agents/tech-researcher.md
---
name: tech-researcher
description: "Tech stack research specialist. Evaluates frameworks, libraries, and tools for real-time data processing and web applications."
model: sonnet
tools: Read, Write, Glob, Grep, WebSearch, WebFetch
maxTurns: 30
memory: project
---

# .claude/agents/architect.md
---
name: architect
description: "System architect for real-time data processing systems. Designs component architecture, data flows, APIs, and database schemas."
model: opus
tools: Read, Write, Edit, Glob, Grep, WebSearch
maxTurns: 40
memory: project
---

# .claude/agents/scaffolder.md
---
name: scaffolder
description: "Project scaffolding specialist. Initializes projects, configures build tools, sets up linting, and creates boilerplate."
model: sonnet
tools: Read, Write, Edit, Bash, Glob, Grep
maxTurns: 30
memory: project
---

# .claude/agents/backend-dev.md
---
name: backend-dev
description: "Backend developer specializing in real-time data processing, WebSocket connections, and API server development."
model: opus
tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch
maxTurns: 80
memory: project
---

# .claude/agents/frontend-dev.md
---
name: frontend-dev
description: "Frontend developer specializing in real-time web dashboards, WebSocket client integration, and responsive UI."
model: opus
tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch
maxTurns: 80
memory: project
---

# .claude/agents/integrator.md
---
name: integrator
description: "Integration specialist. Connects frontend to backend, performs E2E testing, and prepares deployment artifacts."
model: opus
tools: Read, Write, Edit, Bash, Glob, Grep
maxTurns: 50
memory: project
---
```

> **Model selection rationale (Absolute Criterion 1)**:
> - `opus` for `@architect`, `@backend-dev`, `@frontend-dev`, `@integrator` — complex analysis, architectural reasoning, and production-quality code generation require highest quality
> - `sonnet` for `@api-researcher`, `@tech-researcher`, `@scaffolder` — systematic data collection and procedural setup tasks where quality difference between opus/sonnet is minimal

### Agent Team (Step 8 — Parallel Development)

```markdown
### Team: dev-pipeline
- **Members**:
  - `@backend-dev` (opus): All backend services — exchange connectors, spread engine, Telegram bot, REST API
  - `@frontend-dev` (opus): All frontend components — dashboard, real-time display, alert settings, Telegram setup
- **Shared Tasks**: `~/.claude/tasks/dev-pipeline/`
- **Coordination**: Team Lead assigns via TaskCreate, teammates report at each Dense Checkpoint, Team Lead validates before next checkpoint
- **SOT**: Team Lead only writes `state.yaml`. Teammates produce code files only.
```

**Context Injection**:
- Backend dev receives: `planning/system-architecture.md` + `planning/api-design.md` + project scaffolding (Pattern A — Full Delegation, input < 50KB)
- Frontend dev receives: `planning/system-architecture.md` + `planning/api-design.md` + project scaffolding (Pattern A — Full Delegation, input < 50KB)

### SOT (State Management)

- **SOT File**: `.claude/state.yaml`
- **Writer**: Orchestrator (Steps 1-7, 9) / Team Lead (Step 8)
- **Agent Access**: Read-only — agents produce output files, never modify SOT directly
- **Quality Adjustment**: Default pattern applied. Backend and frontend teammates are fully independent (no shared state between them during development); API contract from Step 5 serves as the interface boundary.

### Slash Commands

```yaml
# .claude/commands/select-tech-stack.md
---
description: "Review tech stack analysis and select preferred options for backend, frontend, database, and tools"
---
Read the tech stack analysis at `research/tech-stack-analysis.md` and the decision matrix at `research/tech-decision-matrix.md`.

Present the recommended tech stack with:
1. Backend framework recommendation with alternatives
2. Frontend framework recommendation with alternatives
3. Database recommendation
4. Supporting tools (Telegram library, exchange client libraries)

Ask the user to confirm or modify each selection.
Record the final selection for the Planning phase.
$ARGUMENTS

# .claude/commands/review-architecture.md
---
description: "Review system architecture and API design before implementation"
---
Read the system architecture at `planning/system-architecture.md` and API design at `planning/api-design.md`.

Present a structured summary:
1. Architecture overview (component diagram)
2. Key design decisions and trade-offs
3. API endpoint summary
4. Database schema overview

Ask the user to:
- Approve as-is, or
- Request specific modifications

$ARGUMENTS
```

### Hooks

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "if test -f \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/block_destructive_commands.py; then python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/scripts/block_destructive_commands.py; fi",
          "timeout": 10
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "if command -v npx >/dev/null 2>&1; then FILE=$(echo $TOOL_INPUT | python3 -c \"import sys,json; print(json.load(sys.stdin).get('file_path',''))\" 2>/dev/null); if [ -n \"$FILE\" ] && echo \"$FILE\" | grep -qE '\\.(ts|tsx|js|jsx|json)$'; then npx prettier --write \"$FILE\" 2>/dev/null; fi; fi",
          "timeout": 15
        }]
      }
    ]
  }
}
```

### Required Skills

- None required beyond existing AgenticWorkflow skills (workflow-generator already used)

### MCP Servers

- None required — all exchange APIs are public REST/WebSocket endpoints accessible via standard HTTP clients

### Runtime Directories

```yaml
runtime_directories:
  # Required — Verification Gate outputs
  verification-logs/:        # step-N-verify.md (L1 verification results)

  # Conditional — enabled features
  pacs-logs/:                # step-N-pacs.md (pACS self-confidence ratings)
  review-logs/:              # step-N-review.md (Adversarial Review results)
  translations/:             # glossary.yaml + *.ko.md (@translator outputs)

  # Workflow-specific
  research/:                 # Step 1-2 research outputs
  planning/:                 # Step 4-5 architecture and design outputs
  temp/:                     # Pre-processing intermediate files (gitignored)
```

### Error Handling

```yaml
error_handling:
  on_agent_failure:
    action: retry_with_feedback
    max_attempts: 3
    escalation: human

  on_validation_failure:
    action: retry_or_rollback
    retry_with_feedback: true
    rollback_after: 3

  on_hook_failure:
    action: log_and_continue

  on_context_overflow:
    action: save_and_recover

  on_teammate_failure:
    attempt_1: retry_same_agent
    attempt_2: replace_with_upgrade
    attempt_3: human_escalation

  exchange_api_specific:
    on_rate_limit: exponential_backoff_with_jitter
    on_connection_drop: reconnect_with_state_recovery
    on_invalid_response: log_and_skip_tick
```
