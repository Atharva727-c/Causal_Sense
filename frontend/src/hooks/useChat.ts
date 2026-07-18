import { useState, useCallback, useRef, useEffect } from 'react'
import type { Chat, Message, UploadedFile, ActiveMode } from '../types'

const API = '/api'

function genId() {
  return `${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`
}

const MOCK_RESPONSES = [
  `## Market Analysis Overview

Based on your query, here is a comprehensive market analysis with predictive scenarios.

### Descriptive Analysis
The current market shows signs of consolidation with moderate volatility. Historical data indicates a **12-month CAGR of 8.3%** with seasonal patterns peaking in Q3.

### Diagnostic Analysis
Key drivers include: macroeconomic indicators, **consumer sentiment index (currently at 72.4)**, and supply chain normalization post-disruption.

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

> **Note:** CausalSense predictions are probabilistic, not deterministic. Always combine with domain expertise.`,

  `## Competitive Landscape Analysis

| Company | Market Share | YoY Change | Trend |
|---------|-------------|------------|-------|
| Leader A | 28.4% | +1.2% | ↑ Growing |
| Leader B | 22.1% | -0.8% | ↓ Declining |
| Challenger C | 15.6% | +2.4% | ↑ Surging |
| Niche D | 9.3% | +0.1% | → Stable |
| Others | 24.6% | -2.9% | ↓ Fragmenting |

### Strategic Scenarios (12-month horizon)

| Scenario | Probability | Key Trigger | Impact |
|----------|-------------|-------------|--------|
| Market consolidation via M&A | 22% | Rising rates, valuation compression | 2-3 players merge |
| New entrant disruption | 11% | VC funding surge in adjacent tech | -5% share for top 2 |
| Regulatory intervention | 8% | Antitrust scrutiny intensifies | Leader A forced divestiture |
| Status quo continuation | 31% | No major macro shift | < 1% share movement |
| Challenger overtakes #2 | 14% | Product launch success | C reaches 20%+ share |
| Foreign market entry | 7% | FX opportunity window | New competitor takes 3-4% |
| Price war | 5% | Demand softening | Margin compression across board |
| Partnership ecosystem shift | 2% | Platform consolidation | Distribution realignment |

> Confidence intervals widen beyond 6 months. Refresh this analysis quarterly.`,
]

export function useChat(uploadedFiles: UploadedFile[]) {
  const [chats, setChats] = useState<Chat[]>(() => {
    const id = `local-${genId()}`
    return [{ id, title: 'New Chat', messages: [], createdAt: new Date() }]
  })
  const [activeChatId, setActiveChatId] = useState<string>(() => {
    const id = `local-${genId()}`
    return id
  })
  const [isLoading, setIsLoading] = useState(false)

  // Maps local chat IDs to backend IDs
  const backendIds = useRef(new Map<string, string>())
  const abortRef = useRef<AbortController | null>(null)
  const initialized = useRef(false)

  // Sync initial local chat with backend
  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    const localId = chats[0]?.id
    if (!localId) return

    fetch(`${API}/chats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New Chat' }),
    })
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (data?.id) backendIds.current.set(localId, data.id)
      })
      .catch(() => {})
  }, [chats])

  const activeChat = chats.find(c => c.id === activeChatId) ?? chats[0]

  const sendMessage = useCallback(
    async (content: string, modes: ActiveMode[] = []) => {
      if (!content.trim() || isLoading) return

      const localChatId = activeChatId
      const streamId = `stream-${genId()}`

      // Optimistic UI: add user message + streaming placeholder immediately
      setChats(prev =>
        prev.map(c =>
          c.id === localChatId
            ? {
                ...c,
                title: c.messages.length === 0 ? content.trim().slice(0, 45) : c.title,
                messages: [
                  ...c.messages,
                  { id: genId(), role: 'user' as const, content: content.trim(), timestamp: new Date() },
                  { id: streamId, role: 'assistant' as const, content: '', timestamp: new Date(), streaming: true },
                ],
              }
            : c
        )
      )
      setIsLoading(true)

      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl

      const updateStream = (text: string) => {
        setChats(prev =>
          prev.map(c =>
            c.id === localChatId
              ? { ...c, messages: c.messages.map(m => (m.id === streamId ? { ...m, content: text } : m)) }
              : c
          )
        )
      }

      const finalizeStream = (finalId?: string) => {
        setChats(prev =>
          prev.map(c =>
            c.id === localChatId
              ? {
                  ...c,
                  messages: c.messages.map(m =>
                    m.id === streamId ? { ...m, id: finalId ?? streamId, streaming: false } : m
                  ),
                }
              : c
          )
        )
        setIsLoading(false)
      }

      // Ensure backend chat exists before sending
      if (!backendIds.current.has(localChatId)) {
        try {
          const r = await fetch(`${API}/chats`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: content.trim().slice(0, 45) }),
            signal: ctrl.signal,
          })
          if (r.ok) {
            const d = await r.json()
            backendIds.current.set(localChatId, d.id)
          }
        } catch {
          /* use local fallback */
        }
      }

      const backendChatId = backendIds.current.get(localChatId) ?? localChatId
      const fileContext = uploadedFiles.map(f => f.name).join(', ')

      try {
        const res = await fetch(`${API}/chats/${backendChatId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: content.trim(), fileContext, mode: modes[0] ?? null }),
          signal: ctrl.signal,
        })

        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        let accumulated = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const event = JSON.parse(line.slice(6))
              if (event.delta) {
                accumulated += event.delta
                updateStream(accumulated)
              } else if (event.event === 'done') {
                finalizeStream(event.assistantMsgId)
              }
            } catch {
              /* skip malformed SSE */
            }
          }
        }

        // Safety finalise in case 'done' event was missing
        finalizeStream()
      } catch (err: unknown) {
        if ((err as Error)?.name === 'AbortError') {
          setIsLoading(false)
          return
        }

        // Mock fallback with simulated streaming
        const mockText = MOCK_RESPONSES[Math.floor(Math.random() * MOCK_RESPONSES.length)]
        const words = mockText.split(/(\s+)/)
        let accumulated = ''
        for (const word of words) {
          if (ctrl.signal.aborted) break
          accumulated += word
          updateStream(accumulated)
          await new Promise(r => setTimeout(r, 12 + Math.random() * 8))
        }
        finalizeStream()
      }
    },
    [activeChatId, isLoading, uploadedFiles]
  )

  const newChat = useCallback(() => {
    const localId = `local-${genId()}`
    const chat: Chat = { id: localId, title: 'New Chat', messages: [], createdAt: new Date() }
    setChats(prev => [chat, ...prev])
    setActiveChatId(localId)

    // Create on backend async
    fetch(`${API}/chats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New Chat' }),
    })
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (data?.id) backendIds.current.set(localId, data.id)
      })
      .catch(() => {})
  }, [])

  return {
    chats,
    activeChat: activeChat ?? { id: '', title: 'New Chat', messages: [], createdAt: new Date() },
    activeChatId,
    setActiveChatId,
    sendMessage,
    newChat,
    isLoading,
  }
}
