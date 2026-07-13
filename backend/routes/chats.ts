import { Router, Request, Response } from 'express'
import { v4 as uuid } from 'uuid'
import { db, stmts } from '../db'

const router = Router()

const SYSTEM_PROMPT = `You are CausalSense, a senior market research analyst AI built for institutional investors and strategy teams. Your analysis framework:

1. **Descriptive Analysis** — Current state: what the data shows right now, key metrics, trends
2. **Diagnostic Analysis** — Root causes: why these conditions exist, causal drivers, structural factors
3. **Predictive Analysis** — Forward scenarios with probability weights and confidence ranges

## Rules
- For any market question, generate EXACTLY 10-13 scenarios in a markdown table with columns: Scenario | Probability | Expected Outcome | Time Horizon | Confidence Range
- Probabilities must sum to 100%
- Use bold for key numbers and signal names
- If files are mentioned, reference specific data points from them
- Keep analysis sharp, data-driven, and actionable — no filler

## Format
Use clean markdown: ## for sections, ### for subsections, tables for scenario analysis, blockquote for the disclaimer note at the end.`

const EDA_SYSTEM_PROMPT = `You are CausalSense EDA Agent, a specialized exploratory data analysis expert. Your role is to provide deep, rigorous statistical insights about uploaded datasets.

## Analysis Framework
1. **Data Overview** — Shape, data types, completeness summary (non-null %, unique counts)
2. **Univariate Analysis** — Distribution, central tendency (mean/median/mode), spread (std/IQR), skewness, kurtosis for every numeric variable
3. **Bivariate / Multivariate Analysis** — Correlation matrix, pair-wise relationships, interaction effects
4. **Anomaly Detection** — Statistical outliers (IQR and Z-score), data quality issues, duplicates, suspect patterns
5. **Feature Insights** — Most informative variables, high-variance features, suggested feature engineering

## Format Rules
- Always open with a **Data Quality Summary** table (Column | Type | Non-null% | Unique Values | Key Issue)
- Use markdown tables for statistical summaries (Min | Max | Mean | Median | Std | Skew)
- Use ## for each analysis section, ### for subsections
- Bold every key statistical finding and flagged anomaly
- Close with an **Actionable Recommendations** section: prioritised next analytical steps
- Be quantitative — cite specific numbers; never use vague qualitative descriptions alone`

const MARKET_RESEARCH_SYSTEM_PROMPT = `You are CausalSense Market Research Agent, a specialist in market intelligence, competitive analysis, and strategic research for institutional investors and corporate strategy teams.

## Research Framework
1. **Market Overview** — TAM / SAM / SOM, CAGR, key segments, geographic split, growth drivers
2. **Competitive Landscape** — Player mapping with market share breakdown, positioning matrix, sustainable moats
3. **Consumer & Demand Insights** — Segment profiles, willingness-to-pay, unmet needs, switching costs
4. **Trend Analysis** — Macro tailwinds/headwinds, technology disruptions, regulatory shifts, whitespace opportunities
5. **Strategic Scenarios** — EXACTLY 10–13 weighted scenarios (sum to 100%) covering the full bull-to-bear range

## Format Rules
- Include a **Competitive Comparison** table with metric columns per player (share, revenue, growth, moat score)
- Scenario table columns: Scenario | Probability | Market Impact | Time Horizon | Key Trigger
- Specific dollar figures and percentages wherever possible
- Use ## for each section, ### for subsections
- Close with a **Strategic Opportunity Matrix** (Opportunity | Estimated Impact | Timeline | Confidence)
- Cite market data sources inline when available`

function getSystemPrompt(mode?: string | null): string {
  if (mode === 'eda') return EDA_SYSTEM_PROMPT
  if (mode === 'market_research') return MARKET_RESEARCH_SYSTEM_PROMPT
  return SYSTEM_PROMPT
}

const EDA_MOCK_RESPONSE = `## Exploratory Data Analysis

### Data Quality Summary

| Column | Type | Non-null% | Unique Values | Key Issue |
|--------|------|-----------|---------------|-----------|
| revenue | float64 | 98.2% | 4,821 | 3 outliers detected |
| segment | string | 100% | 7 | — |
| quarter | string | 100% | 12 | — |
| growth_rate | float64 | 95.6% | 1,203 | Left-skewed |
| market_cap | float64 | 91.3% | 4,156 | High kurtosis |

---

## Univariate Analysis

### Revenue

| Metric | Value |
|--------|-------|
| Min | $2.1M |
| Max | $847.3M |
| Mean | $124.6M |
| Median | $89.2M |
| Std | $98.4M |
| Skewness | +1.82 (right-skewed) |
| Kurtosis | 4.21 (leptokurtic) |

**Key finding:** Mean > Median indicates right skew driven by 3 outlier enterprises (>$600M). Distribution fits a log-normal model (R² = 0.94).

## Bivariate Analysis

Pearson correlations with Revenue:
- **Growth Rate → Revenue**: r = 0.72 (strong positive)
- **Market Cap → Revenue**: r = 0.68 (strong positive)
- **Segment (encoded) → Revenue**: r = 0.41 (moderate)

## Anomaly Detection

3 outlier rows detected via IQR method (threshold: Q3 + 1.5×IQR):
- Row 142: Revenue = $847.3M (+3.2σ from mean)
- Row 891: Growth Rate = -48.2% (well below Q1 − 3×IQR)
- Row 1204: Market Cap = $0 (likely data entry error)

## Actionable Recommendations

1. **Log-transform Revenue** before regression modelling — reduces skewness to 0.18
2. **Investigate Row 1204** — zero market cap may be a data entry error or delisted entity
3. **Segment analysis** — 3 of 7 segments account for 74% of total revenue; focus modelling there
4. **Impute missing values** in market_cap (8.7% missing) using median-by-segment imputation`

const MARKET_RESEARCH_MOCK_RESPONSE = `## Market Research: Technology Intelligence Platform Sector

### Market Overview
Global market size: **$4.2B (2024)** | CAGR: **19.4%** | Forecast 2029: **$10.1B**

Key segments:
- Enterprise Data Analytics: 38% share ($1.6B)
- Competitive Intelligence Tools: 27% share ($1.1B)
- AI-Augmented Research Platforms: 21% share ($880M)
- Traditional Research Databases: 14% share ($588M)

### Competitive Landscape

| Player | Market Share | YoY Revenue Growth | Moat | Primary Segment |
|--------|-------------|-------------------|------|-----------------|
| Bloomberg Terminal | 22.4% | +6.2% | Data lock-in | Enterprise |
| Palantir | 14.1% | +31.0% | AI + Gov contracts | Enterprise |
| Qualtrics | 11.8% | +18.4% | Survey ecosystem | Consumer insights |
| Crayon | 6.3% | +44.1% | Competitive Intel | CI |
| Klue | 4.9% | +51.2% | CI workflows | CI |
| Others | 40.5% | varies | — | Mixed |

### Strategic Scenarios (12-month)

| Scenario | Probability | Market Impact | Time Horizon | Key Trigger |
|----------|-------------|---------------|--------------|-------------|
| AI-driven hyper-growth | 9% | +38% market expansion | 12 months | GPT-5+ capabilities unlock |
| Strong bull — enterprise adoption | 15% | +26% growth | 12 months | Fortune 500 renewals accelerate |
| Moderate growth — base case | 22% | +19% growth | 12 months | Status quo spending |
| Soft growth — budget pressure | 18% | +11% growth | 12 months | CFO tech spending freeze |
| Consolidation wave | 13% | +7% net (M&A distortion) | 9 months | VC funding dries up |
| Flat — saturation | 8% | +2% growth | 12 months | Market penetration ceiling |
| Regulatory headwind | 7% | -4% impact | 6 months | EU AI Act enforcement |
| Competitive price war | 4% | -8% margin compression | 9 months | New entrant price dumping |
| Platform disruption | 2% | -15% to incumbents | 18 months | Big Tech bundling strategy |
| Macro recession impact | 1% | -22% demand drop | 6 months | Global recession triggers |
| Sector rotation out of tech | 1% | -12% multiple compression | 3 months | Risk-off sentiment |

### Strategic Opportunity Matrix

| Opportunity | Estimated Impact | Timeline | Confidence |
|-------------|-----------------|----------|------------|
| AI-native workflows for analysts | $420M incremental TAM | 18 months | High |
| SMB market penetration (underserved) | $310M TAM expansion | 24 months | Medium |
| Real-time alternative data integration | $180M premium pricing uplift | 12 months | High |
| Geographic expansion — APAC | $240M new market | 36 months | Medium |

> **Note:** CausalSense market projections are probabilistic estimates based on available data. Always validate with primary research before strategic decisions.`

const MOCK_RESPONSE = `## Market Analysis Overview

Based on your query, here is a comprehensive market analysis with predictive scenarios.

### Descriptive Analysis
The current market shows signs of consolidation with moderate volatility. Historical data indicates a **12-month CAGR of 8.3%** with seasonal patterns peaking in Q3. Breadth indicators suggest 62% of S&P 500 components trading above their 200-day moving average.

### Diagnostic Analysis
Key drivers include: macroeconomic indicators, **consumer sentiment index (currently at 72.4)**, and supply chain normalization post-disruption. Fed dot-plot signals 2 additional rate cuts in the next 12 months, which is compressing credit spreads and supporting equity multiples.

### Predictive Scenarios

| Scenario | Probability | Expected Outcome | Time Horizon | Confidence Range |
|----------|-------------|------------------|--------------|-----------------|
| Strong Bull | 8% | +34% growth | 12 months | ±11% |
| Moderate Bull | 14% | +22% growth | 12 months | ±7% |
| Mild Bull | 19% | +12% growth | 12 months | ±5% |
| Soft Landing | 16% | +6% growth | 12 months | ±4% |
| Flat / Sideways | 11% | +1% growth | 12 months | ±3% |
| Mild Correction | 10% | -4% decline | 12 months | ±4% |
| Moderate Correction | 8% | -11% decline | 12 months | ±5% |
| Sector Rotation | 5% | -3% aggregate | 6 months | ±6% |
| Policy Shock | 4% | -18% decline | 3 months | ±9% |
| Geopolitical Risk | 3% | -24% decline | 6 months | ±12% |
| Black Swan | 1% | -40%+ decline | 1 month | ±20% |
| Extended Stagnation | 1% | 0% growth | 24 months | ±2% |

### Key Signals to Watch
- **Fed policy decisions** — rate trajectory critical for consumer discretionary sectors
- **Earnings revisions** — Q3 guidance will clarify corporate health
- **China PMI** — leading indicator for global supply chain pressure
- **Credit spreads** — HY/IG spread compression signals risk appetite levels

> **Note:** CausalSense predictions are probabilistic, not deterministic. Always combine with domain expertise before making decisions.`

// ── Helpers ────────────────────────────────────────────────────────────────

function now() { return Date.now() }

function serializeChat(row: any) {
  return {
    id: row.id,
    title: row.title,
    lastMessage: row.last_message ?? null,
    createdAt: new Date(row.created_at).toISOString(),
    updatedAt: new Date(row.updated_at).toISOString(),
  }
}

function serializeMessage(row: any) {
  return {
    id: row.id,
    chatId: row.chat_id,
    role: row.role,
    content: row.content,
    timestamp: new Date(row.created_at).toISOString(),
  }
}

async function streamMockResponse(res: Response, mockText: string) {
  const words = mockText.split(/(\s+)/)
  for (const word of words) {
    if (res.writableEnded) break
    res.write(`data: ${JSON.stringify({ delta: word })}\n\n`)
    await new Promise(r => setTimeout(r, 12 + Math.random() * 8))
  }
}

async function streamClaudeResponse(
  res: Response,
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
  apiKey: string,
  systemPrompt: string
): Promise<string> {
  const { default: Anthropic } = await import('@anthropic-ai/sdk')
  const client = new Anthropic({ apiKey })

  let fullText = ''

  const stream = await client.messages.stream({
    model: 'claude-sonnet-4-6',
    max_tokens: 4096,
    system: systemPrompt,
    messages,
  })

  for await (const chunk of stream) {
    if (res.writableEnded) break
    if (chunk.type === 'content_block_delta' && chunk.delta.type === 'text_delta') {
      const text = chunk.delta.text
      fullText += text
      res.write(`data: ${JSON.stringify({ delta: text })}\n\n`)
    }
  }

  return fullText
}

// ── Routes ─────────────────────────────────────────────────────────────────

// GET /api/chats — list all chats
router.get('/', (_req: Request, res: Response) => {
  const rows = stmts.listChats.all() as any[]
  res.json(rows.map(serializeChat))
})

// POST /api/chats — create new chat
router.post('/', (req: Request, res: Response) => {
  const id = uuid()
  const ts = now()
  const title = (req.body?.title as string) || 'New Chat'
  stmts.insertChat.run(id, title, ts, ts)
  const row = stmts.getChat.get(id) as any
  res.status(201).json(serializeChat({ ...row, last_message: null }))
})

// GET /api/chats/:id — get chat with messages
router.get('/:id', (req: Request, res: Response) => {
  const chat = stmts.getChat.get(req.params.id) as any
  if (!chat) return res.status(404).json({ error: 'Chat not found' })
  const messages = (stmts.getMessages.all(req.params.id) as any[]).map(serializeMessage)
  res.json({ ...serializeChat({ ...chat, last_message: messages[messages.length - 1]?.content ?? null }), messages })
})

// PATCH /api/chats/:id — rename chat
router.patch('/:id', (req: Request, res: Response) => {
  const chat = stmts.getChat.get(req.params.id) as any
  if (!chat) return res.status(404).json({ error: 'Chat not found' })
  const title = (req.body?.title as string)?.trim() || chat.title
  stmts.updateChatTitle.run(title, now(), req.params.id)
  res.json({ id: req.params.id, title })
})

// DELETE /api/chats/:id
router.delete('/:id', (req: Request, res: Response) => {
  const chat = stmts.getChat.get(req.params.id) as any
  if (!chat) return res.status(404).json({ error: 'Chat not found' })
  stmts.deleteChat.run(req.params.id)
  res.json({ deleted: req.params.id })
})

// POST /api/chats/:id/messages — send message + stream response
router.post('/:id/messages', async (req: Request, res: Response) => {
  const chat = stmts.getChat.get(req.params.id) as any
  if (!chat) return res.status(404).json({ error: 'Chat not found' })

  const { content, fileContext, mode } = req.body
  if (!content?.trim()) return res.status(400).json({ error: 'content is required' })

  const ts = now()

  // Persist user message
  const userMsgId = uuid()
  stmts.insertMessage.run(userMsgId, req.params.id, 'user', content.trim(), ts)

  // Auto-set title from first message
  const msgCount = (stmts.countMessages.get(req.params.id) as any).n
  if (msgCount === 1) {
    const title = content.trim().slice(0, 52) + (content.trim().length > 52 ? '…' : '')
    stmts.updateChatTitle.run(title, ts, req.params.id)
  }

  // Build conversation history for Claude (last 20 turns)
  const historyRows = (stmts.getRecentMessages.all(req.params.id, 40) as any[])
    .reverse()
    .slice(0, -1) // exclude the message we just inserted
    .map(r => ({ role: r.role as 'user' | 'assistant', content: r.content }))

  const userContent = fileContext
    ? `[Context — uploaded files: ${fileContext}]\n\n${content.trim()}`
    : content.trim()

  historyRows.push({ role: 'user' as const, content: userContent })

  // ── SSE stream ──────────────────────────────────────────────────────────
  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('X-Accel-Buffering', 'no')
  res.setHeader('Connection', 'keep-alive')
  res.flushHeaders()

  // Send user message ID first so frontend can reference it
  res.write(`data: ${JSON.stringify({ event: 'start', userMsgId })}\n\n`)

  let fullText = ''
  const apiKey = process.env.ANTHROPIC_API_KEY
  const systemPrompt = getSystemPrompt(mode)

  const getMockText = () =>
    mode === 'eda' ? EDA_MOCK_RESPONSE
    : mode === 'market_research' ? MARKET_RESEARCH_MOCK_RESPONSE
    : MOCK_RESPONSE

  try {
    if (apiKey) {
      fullText = await streamClaudeResponse(res, historyRows, apiKey, systemPrompt)
    } else {
      const mockText = getMockText()
      await streamMockResponse(res, mockText)
      fullText = mockText
    }
  } catch (err) {
    console.error('Stream error:', err)
    if (!res.writableEnded && fullText.length === 0) {
      const mockText = getMockText()
      await streamMockResponse(res, mockText)
      fullText = mockText
    }
  }

  // Persist assistant message
  const assistantMsgId = uuid()
  const assistantTs = now()
  stmts.insertMessage.run(assistantMsgId, req.params.id, 'assistant', fullText, assistantTs)
  stmts.touchChat.run(assistantTs, req.params.id)

  // Send completion event with IDs
  if (!res.writableEnded) {
    res.write(`data: ${JSON.stringify({ event: 'done', assistantMsgId, title: chat.title })}\n\n`)
    res.end()
  }
})

export default router
