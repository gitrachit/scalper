# GOAT-Level Gold Scalper: A Realistic Blueprint for a Claude-in-the-Loop XAUUSD System on XM MT5

## TL;DR
- **Build it as a learning project, not a money machine.** The rigorous evidence — DeepFund's leakage-free live test (even DeepSeek-V3 and Claude-3.7-Sonnet incurred *net trading losses*; only 1 of 9 flagship LLMs was profitable over 24 trading days), FINSABER's 20-year/100+ symbol study (LLM "alpha" vanishes; Buy-and-Hold significantly outperforms), and ESMA data that 74–89% of retail CFD accounts lose money — says an LLM-driven retail gold scalper is very unlikely to be reliably profitable. Your own prior negative walk-forward result on gold is the norm, not bad luck.
- **The only defensible architecture is a hybrid:** a deterministic Python/MQL5 execution-and-risk engine that the LLM CANNOT override, with Claude Fable 5 sitting OUT of the hot path — used for end-of-day journaling analysis and slow, human-gated strategy proposals on M5/M15 bars, never tick-level. LLM inference latency (seconds) makes true tick scalping impossible.
- **Spend the first months proving results cheaply.** Backtest on Dukascopy tick data → forward-test on the XM demo behind a hard risk engine → only consider real money if a pre-registered walk-forward + forward-test edge survives costs. On a $1,000 account with XM's ~$0.27–0.50/oz gold spread, the cost math is hostile for small scalp targets.

## Key Findings

**1. Existing MT5 MCP servers exist and work, but most are unsafe for automated live trading as-is.** The main open-source options are `ariadng/metatrader-mcp-server` (79 stars, MIT license, full order execution via an EA REST bridge on port 18080), `Qoyyuum/mcp-metatrader5-server` (FastMCP, exposes `order_send`), and `Cloudmeru/MetaTrader-5-MCP-Server` (deliberately **read-only** — trading calls explicitly blocked, the safest for analysis). All require the `MetaTrader5` Python package, which is **Windows-only**, so you need a Windows VPS or VM.

**2. Gold scalping economics on $1,000 are hostile.** XAUUSD moves 200–500+ pips/day, best during the London–NY overlap. XM's gold spread is roughly $0.27–$0.50/oz (Ultra Low ~$0.27–0.30, Standard ~$0.50) — that is 27–50 "pips." A 0.01-lot trade has a pip value of $0.01, [Ultima Markets](https://www.ultimamarkets.com/academy/what-is-1-pip-in-xauusd-how-to-calculate/) so a 100-pip ($1) target = $1.00 gross, minus 27–50 pips of spread cost. The spread tax is proportionally catastrophic on small targets, which is precisely why most retail scalpers bleed out.

**3. LLM latency forces M5/M15, not ticks.** A Claude Fable 5 call takes seconds; M1 bars close every 60 seconds. Realistic LLM cadence is one analysis per closed M5 or M15 bar, or event-driven — not per tick.

**4. The self-improvement loop is real but dangerous.** Reflexion-style self-reflection (as in TradingGroup, FinMem) can catch process errors, but it drifts and overfits on tiny samples. Daily "improvement" on 3–10 trades is statistical noise, not learning, and requires strict "memory hygiene."

**5. API cost is not your constraint — edge is.** Claude Fable 5 is $10/$50 per million input/output tokens (Opus 4.8 is half at $5/$25; Sonnet 5 is $3/$15, or $2/$10 intro through Aug 31, 2026). Daily EOD analysis costs cents to ~$1/day; even per-M5-bar analysis during the overlap with prompt caching is a few dollars/day at most.

## Details

### 1. Architecture

**Four candidate designs, evaluated:**

**(a) Pure MQL5 EA, rules only.** Fastest (microsecond execution, runs natively on the chart), best for real scalping, and needed anyway for the deterministic risk layer. But no LLM reasoning and no self-improvement beyond parameter optimization. *Verdict: this is your execution + risk core, not the whole system.*

**(b) Python bridge (`MetaTrader5` package) + Claude API.** The official `MetaTrader5` pip package connects Python to a running MT5 terminal (Windows-only). You pull rates/ticks, compute features in pandas, call Claude, and send orders via `order_send()`. Flexible, full control, trivial to log everything to a database. *Verdict: recommended backbone for the analytical/decision layer.* Note MT5 has a setting "Disable automatic trading via external Python API" (returns error 10027, TRADE_RETCODE_CLIENT_DISABLES_AT) — you can keep MQL-side execution as a fallback and selectively block the Python path.

**(c) MCP server connecting Claude directly to MT5.** Elegant for interactive exploration ("show me XAUUSD M15, analyze my open positions"). But handing an LLM direct `order_send` authority inside an automated loop is the single most dangerous choice — no deterministic gate. *Verdict: use MCP for interactive/manual analysis (and the read-only Cloudmeru server for safe data access); do NOT let the MCP layer place automated live orders.*

**(d) Hybrid: deterministic engine + LLM analyst/strategist behind a hard risk gate.** *This is the recommendation.* The LLM proposes; hard-coded logic disposes. Every LLM output is a structured suggestion (direction, entry, SL, TP, size-request, confidence) that must pass a deterministic risk validator before any order. The risk engine is pure code, unit-tested, and the LLM has no API path to bypass it.

**Where the LLM should and should NOT sit:**
- ✅ End-of-day journal analysis and pattern-finding.
- ✅ Slow, human-approved strategy/parameter proposals (weekly, not per-trade).
- ✅ Optional per-bar "veto/context" on M5/M15 (regime read, news awareness), gated.
- ❌ Tick-level entries/exits (latency).
- ❌ Position sizing or risk decisions (must be deterministic).
- ❌ Any ability to widen stops, add to losers, or disable the kill-switch.

**Recommended stack:** Windows VPS → MT5 terminal (XM demo) → Python service (`MetaTrader5` package) that (i) computes features on closed M5/M15 bars, (ii) runs a deterministic strategy + risk engine in code, (iii) optionally queries Claude for context/veto with a strict timeout and a safe default (do-nothing) on timeout, (iv) logs everything to SQLite/Postgres. A separate nightly job runs the Claude journaling/improvement loop and writes proposed config changes to a **staging** file that a human must promote.

### 2. Gold Scalping Strategy Research

- **Sessions:** Highest volatility and tightest spreads during the London–NY overlap, ~12:00–16:00 GMT; per one gold-strategy source, gold's daily high or low is established in this window roughly 70% of the time. Asian session (00:00–07:00 GMT) is quiet and range-bound; spreads widen to $0.80–$2.00+. For an India-based developer, the overlap is ~17:30–21:30 IST — convenient timing.
- **Volatility:** Gold routinely ranges 200–500 pips/day ($2–$5), and 1,000+ pips on NFP/CPI/FOMC days. Use ATR (e.g., 10-day; scale size down when ATR > $30) to size stops and gate trading.
- **XM costs:** Ultra Low ~$0.27–0.30/oz spread with no commission; Standard ~$0.50/oz; Zero ~$0.16 + $3.50/lot/side (~$7 round trip). Swaps apply overnight (intraday scalping avoids them; an Islamic swap-free account is available). Spreads widen during news and thin Asian hours.
- **Common strategies:** Asian-range breakout into London/NY; VWAP mean-reversion; momentum on the overlap; SMC/order-flow (popular but hard to automate reliably). Honest sustained edges after costs are rare for retail scalping.
- **Why most gold scalpers lose:** spread is proportionally huge on small targets; overtrading (40+ trades = 40× spread tax); news spikes; and tight stops sitting in liquidity-sweep zones. The demo-to-live gap is widest for scalping because friction dominates.

### 3. Self-Improvement Loop

**Design:**
- **Structured journaling:** log every trade with features — setup type, session, entry/exit price and time, spread at entry, ATR, SL/TP, MFE/MAE, outcome, and the LLM's rationale if any. This is exactly the "high-quality post-training data" [arXiv](https://arxiv.org/abs/2508.17565) TradingGroup emphasizes as missing from most systems.
- **EOD Claude analysis:** feed the day's journal plus running aggregate stats to Claude; ask for observations, one hypothesis, and *proposed* rule/param changes with explicit reasoning.
- **Guardrails against destructive drift:**
  - **No auto-apply.** Proposals go to a staging config; you promote them.
  - **Walk-forward validation required** before any change is accepted — re-run on out-of-sample data.
  - **Minimum sample sizes.** Don't act on fewer than ~30 trades per bucket; daily changes on 3–10 trades are noise.
  - **Memory hygiene** (versioned lessons, scoring, decay) — Reflexion-style agents store *bad* lessons without curation, which then mislead future decisions.
  - **Change budget & rollback.** Limit to one validated parameter change per cycle; keep git-versioned configs and auto-rollback on live degradation.

**What the research actually shows (be sober):** TradingGroup and FinMem report strong *backtest* gains (FinMem: TSLA cumulative return 61.78% with Sharpe 2.68 vs Buy-and-Hold −18.63% [arxiv](https://arxiv.org/pdf/2311.13743) in their window; [arxiv](https://arxiv.org/pdf/2311.13743) TradingGroup AMZN CR 40.46% vs 13.27% best baseline). [The Moonlight](https://www.themoonlight.io/en/review/tradinggroup-a-multi-agent-trading-system-with-self-reflection-and-data-synthesis) But these are short, stock-only, in-sample-adjacent windows. Independent, bias-controlled evaluations (Section 6) demolish the generalization.

### 4. Risk Management for $1,000 (hard-coded, non-overridable)

**Gold contract math (XM):** 1 standard lot = 100 oz; 1 pip = $0.01 price move; pip value = $1.00/lot, [Ultima Markets](https://www.ultimamarkets.com/academy/what-is-1-pip-in-xauusd-how-to-calculate/) $0.10 for 0.10 lot, **$0.01 for 0.01 lot** (the minimum). Micro accounts: 1 lot = 10 oz, min 0.1 lot = 1 oz (same $0.01/pip minimum exposure).

**Position sizing formula:** `Lot = RiskAmount / (StopLossPips × PipValuePerLot)`. Example: $1,000 account, risk 1% = $10, stop $3.00 (300 pips). Lot = 10 / (300 × $1.00) = **0.033 → round down to 0.03 lots**. A $3 adverse move = ~$9 loss ≈ 0.9%. On $1,000 you are essentially forced into 0.01–0.03 lots — which is healthy discipline.

**Hard deterministic limits (code, not LLM):**
- Max risk/trade: 0.5–1% ($5–$10).
- Max daily loss: 3% ($30) → kill-switch halts trading until next day.
- Max concurrent trades: 1–2.
- Max trades/day: cap (e.g., 5) to fight overtrading.
- **News filter:** query an economic calendar API — Forex Factory's free community JSON/ML API, Trading Economics, FXStreet, or MT5's built-in MQL5 economic calendar functions — and block new entries ±15–30 min around high-impact USD events (NFP, CPI, FOMC).
- **Drawdown kill-switch:** halt at, e.g., 10% total drawdown; require manual restart + review.
- **Spread gate:** reject entries when live spread exceeds a threshold (e.g., > $0.60/oz).

### 5. Implementation Specifics

- **MetaTrader5 Python package:** Windows-only; requires the MT5 terminal running with "Allow algorithmic trading" enabled. Non-Windows development requires a Windows VPS/VM.
- **VPS (India):** Latency matters far less for M5/M15 than for tick scalping — place the VPS near XM's server region rather than near you. Options: India-based providers such as VCCLHosting (from ₹274/mo, Kolhapur DC) or DedicatedCore (Hyderabad); global forex VPS such as AccuWeb (from $7.99/mo, has a Hyderabad location) or InterServer (~$10/mo, Windows Server 2022, ~3 ms to NY hubs).
- **MCP servers (GitHub):** `ariadng/metatrader-mcp-server` (execution, MIT, EA REST bridge, 79★); `Qoyyuum/mcp-metatrader5-server` (FastMCP, `order_send`); `Cloudmeru/MetaTrader-5-MCP-Server` (**read-only, safest**, blocks all trading calls); `ali-rajabpour/metatrader-mcp` (real chart screenshots for vision analysis); `PHUICMT/mcp-mt5` (build/backtest pipeline — compile EAs, run Strategy Tester, parse reports via an LLM). Audit any before granting order authority.
- **Claude API cost:** Fable 5 $10/$50 per MTok [BenchLM](https://benchlm.ai/anthropic/api-pricing) ; Opus 4.8 $5/$25 (likely sufficient and cheaper); Sonnet 5 $3/$15 (intro $2/$10 through Aug 31, 2026) is the sensible workhorse. EOD analysis ≈ cents/day. Per-M5-bar analysis during the ~4-hour overlap (~48 bars) with caching is still only a few dollars/day. Use prompt caching (up to 90% off cached input) and the Batch API (50% off) for the nightly loop.
- **Prompt/context design:** feed Claude structured JSON (OHLCV, indicators, session, live spread, open positions, recent journal stats); require structured JSON out (a proposal object with direction, SL, TP, size-request, confidence, rationale). Keep the fixed instruction block cached. Feed only point-in-time data.
- **Backtesting:** MT5 Strategy Tester with "Every tick based on real ticks." Broker tick data is often incomplete (users report ~60% quality over long ranges, vs a 99.9% benchmark); import **Dukascopy** tick data (via Tick Data Suite, Tickstory, or StrategyQuant's free Quant Data Manager) into a custom symbol for 99–100% modeling quality — essential for scalping where spread/slippage dominate. Cross-validate in Python (backtesting.py, vectorbt) with realistic cost/slippage models.
- **Backtesting an LLM strategy is hard:** every decision is an API call, so a vectorized backtest becomes hours of round-trips. Mitigate by deciding less often (per-bar), caching aggressively, and pre-generating LLM outputs. **Critical: LLM look-ahead bias** — the model has memorized historical prices/outcomes (Lopez-Lira et al. showed GPT-4o recalls S&P 500 closes to within <1% for in-training dates). Only **forward-testing on data after the model's training cutoff** is trustworthy for an LLM system.

### 6. Reality Check (evidence-based)

- **Live LLM fund test — DeepFund (arXiv:2505.11065, NeurIPS 2025 Datasets & Benchmarks Track):** the authors ran a deliberately leakage-free live window "from March 17 to April 17, 2025, covering 24 trading days," using data published after each model's pretraining cutoff. Result: 8 of 9 flagship LLMs posted negative cumulative returns; only Grok 3 was positive; passive Buy-and-Hold was more resilient. The paper states that "even cutting-edge models such as DeepSeek-V3 and Claude-3.7-Sonnet incur net trading losses within DeepFund['s] real-time evaluation environment, underscoring the present limitations of LLMs for active fund management."
- **FINSABER (Li, Kim, Cucuringu, Ma — arXiv:2505.07078, KDD 2026):** over two decades and 100+ symbols with survivorship/look-ahead/data-snooping mitigation, LLM advantages "deteriorate significantly," and Buy-and-Hold "significantly outperforms both LLM strategies across all robust setups." [arXiv](https://arxiv.org/html/2505.07078v3) Regime Sharpe ratios were dismal: "FinAgent records Sharpe 0.12 in bulls and −0.38 in bears; FinMem gets −0.19 and −0.97. [arXiv](https://arxiv.org/html/2505.07078v3) " Their conclusion: reported LLM alpha "is likely a methodological artefact of narrow, biased evaluations." [arxiv](https://arxiv.org/pdf/2505.07078)
- **TradingAgents (arXiv:2412.20138):** claimed spectacular backtest numbers (e.g., AAPL CR 26.62%, Sharpe 8.21; GOOGL CR 24.36%, Sharpe 6.39) — but only over a single stock-only quarter on tech mega-caps. The authors themselves flagged the Sharpe as anomalously high (above their own "excellent" threshold of 3) and never live-traded it. This is the pattern to distrust.
- **Retail base rates:** ESMA's product-intervention analysis found "74–89% of retail investment accounts typically lose money... with average losses per client ranging from €1,600 to €29,000"; the CFTC reports ~70–80% of US retail forex traders are unprofitable. India's SEBI study (Sep 23, 2024) found 93% of individual equity-F&O traders lost money in FY22–FY24 (aggregate losses over ₹1.8 lakh crore; only ~7% profitable), and that "97 per cent of FPI profits and 96 per cent of proprietary trader profits came from algorithmic trading" — i.e., retail is on the losing side of institutional algos. Prop-firm challenge pass rates are below 10%, with only ~7% ever receiving a payout; scalping shows the widest demo-to-live gap because spread/friction dominates small targets.

**Realistic expectations:** Treat this as a systems-engineering and market-microstructure learning project with a high probability of no durable profit. The value is in building a rigorous, reusable research/execution/risk framework and internalizing validation discipline — not in the $1,000 growing. Your prior negative walk-forward on gold is fully consistent with the entire independent literature; hold new ideas to exactly that standard.

## Recommendations

**Phase 0 — Framework (weeks 1–3).** Windows VPS + MT5 (XM demo) + Python `MetaTrader5` service. Build the deterministic risk engine FIRST (position sizing, daily loss limit, kill-switch, spread gate, news filter) with unit tests. Build structured journaling to a database. No LLM yet. *Benchmark to proceed: risk engine passes tests and correctly refuses out-of-bounds orders in a simulated stress run.*

**Phase 1 — Backtest a rules baseline (weeks 3–6).** Import Dukascopy XAUUSD tick data; implement 1–2 simple, well-understood strategies (Asian-range breakout on the overlap; VWAP reversion). Backtest with real costs (XM spread ~$0.27–0.50 + slippage). **Pre-register your success criteria before optimizing.** If the rules baseline has no edge after costs, that is the expected result — do not over-optimize to manufacture one.

**Phase 2 — Add Claude as analyst (weeks 6–10).** Wire Claude Fable 5 (or the cheaper Opus 4.8 / Sonnet 5) for EOD journaling analysis and optional gated M5/M15 context/veto. Keep the deterministic engine authoritative. Run the self-improvement loop in **staging-only** mode (proposals require human promotion).

**Phase 3 — Forward test on demo (≥ 3 months, ≥ 100 trades).** This is the ONLY trustworthy validation for an LLM system (post-training-cutoff data). Track expectancy, profit factor, max drawdown, and — critically — whether the self-improvement loop beats a **frozen** baseline config running in parallel.

**Phase 4 — Go/No-Go.** Consider real money ONLY if ALL hold: forward-test expectancy positive after costs over ≥100 trades AND ≥3 months, survives walk-forward, and the LLM loop demonstrably beats the frozen baseline. Otherwise keep it a demo/learning system.

**Thresholds that change the plan:** Demo expectancy negative after 100 trades → stop adding complexity, revert to rules, or shelve. Self-improvement loop underperforms the frozen config → disable auto-proposals. Profit factor < 1.1 or max drawdown > 15% → no real money.

## Caveats
- Several XM spread figures come from affiliate/marketing sites; treat exact numbers as approximate and verify against your own XM demo's live spread and the XAUUSD symbol specification.
- Backtest results (even at 99% modeling quality) systematically overstate scalping performance; the demo-to-live gap is widest for scalping.
- Published LLM trading research skews toward positive results; the independent, bias-controlled work (FINSABER, DeepFund) is more credible and is negative.
- "Claude Fable 5" pricing/availability were reported as recently variable (suspended then restored around July 1, 2026); confirm current model access and rates — and consider that Opus 4.8/Sonnet 5 are cheaper and likely sufficient — before budgeting.
- Automated trading via the MetaTrader5 Python API and third-party MCP servers carries operational risk (disconnects, partial fills, bugs, and — for execution-capable MCP servers — the danger of an ungated LLM order). The hard-coded kill-switch and deterministic risk engine are non-negotiable.