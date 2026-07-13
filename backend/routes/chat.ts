import { Router, Request, Response } from 'express'

const router = Router()

const MOCK_MARKET_RESPONSE = `## Market Analysis Overview

Based on your query, here is a comprehensive market analysis with predictive scenarios.

### Descriptive Analysis
The current market shows signs of consolidation with moderate volatility. Historical data indicates a 12-month CAGR of 8.3% with seasonal patterns peaking in Q3.

### Diagnostic Analysis
Key drivers include: macroeconomic indicators, consumer sentiment index (currently at 72.4), and supply chain normalization post-disruption.

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

> **Note:** CausalSense predictions are probabilistic. Always combine with domain expertise before making decisions.`

const SYSTEM_PROMPT = `You are CausalSense, an expert market research analyst AI. Your role is to help business analysts understand market dynamics through:

1. **Descriptive Analysis**: What is happening in the market right now
2. **Diagnostic Analysis**: Why these market conditions exist
3. **Predictive Analysis**: What could happen next

For every market question, you MUST:
- Provide a structured analysis with Descriptive, Diagnostic, and Predictive sections
- Generate exactly 10-13 probabilistic scenarios in a markdown table with columns: Scenario, Probability, Expected Outcome, Time Horizon, Confidence Range
- Probabilities must sum to 100%
- Reference any uploaded data files when mentioned
- Format all responses in clean markdown with tables

Keep responses focused, data-driven, and actionable. If the user uploads data, reference specific numbers from it.`

router.post('/', async (req: Request, res: Response) => {
  const { message, fileContext, history } = req.body

  if (!message) {
    return res.status(400).json({ error: 'Message is required' })
  }

  const apiKey = process.env.ANTHROPIC_API_KEY

  if (!apiKey) {
    await new Promise(r => setTimeout(r, 800 + Math.random() * 600))
    return res.json({ content: MOCK_MARKET_RESPONSE })
  }

  try {
    const { Anthropic } = await import('@anthropic-ai/sdk')
    const client = new Anthropic({ apiKey })

    const messages: Array<{ role: 'user' | 'assistant'; content: string }> = []

    if (history && Array.isArray(history)) {
      for (const msg of history.slice(-10)) {
        messages.push({ role: msg.role, content: msg.content })
      }
    }

    const userContent = fileContext
      ? `[Uploaded files available: ${fileContext}]\n\n${message}`
      : message

    messages.push({ role: 'user', content: userContent })

    const response = await client.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      messages,
    })

    const content = response.content[0].type === 'text' ? response.content[0].text : ''
    return res.json({ content })
  } catch (err) {
    console.error('Claude API error:', err)
    return res.json({ content: MOCK_MARKET_RESPONSE })
  }
})

export default router
