import { useState, useCallback, useRef, useEffect } from 'react'
import type { Chat, Message, UploadedFile, ActiveMode, FeatureId } from '../types'

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

// One stable id shared by the initial chat and activeChatId — generating two
// different ids here meant the first chat could never receive messages.
const INITIAL_CHAT_ID = `local-${genId()}`

export function useChat(uploadedFiles: UploadedFile[]) {
  const [chats, setChats] = useState<Chat[]>(() => [
    { id: INITIAL_CHAT_ID, title: 'New Chat', messages: [], createdAt: new Date() },
  ])
  const [activeChatId, setActiveChatId] = useState<string>(INITIAL_CHAT_ID)
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

  // ── Shared message helpers ────────────────────────────────────────────────
  // Tracks which chats already have a backend EDA session (for follow-ups).
  const edaSessions = useRef(new Map<string, string>())

  const appendMessages = useCallback((localChatId: string, msgs: Message[]) => {
    setChats(prev =>
      prev.map(c => (c.id === localChatId ? { ...c, messages: [...c.messages, ...msgs] } : c))
    )
  }, [])

  const patchMessage = useCallback(
    (localChatId: string, msgId: string, patch: Partial<Message>) => {
      setChats(prev =>
        prev.map(c =>
          c.id === localChatId
            ? { ...c, messages: c.messages.map(m => (m.id === msgId ? { ...m, ...patch } : m)) }
            : c
        )
      )
    },
    []
  )

  // Feature intent in a typed message (used when no mode chip is active).
  const detectFeature = (content: string): FeatureId | null => {
    const t = content.toLowerCase()
    if (/market\s*research/.test(t)) return 'market_research'
    if (/\beda\b|exploratory\s+data/.test(t)) return 'eda'
    if (/insight\s*builder/.test(t)) return 'insight_builder'
    return null
  }

  // Pick the dataset a message refers to: a filename mentioned in the text
  // (e.g. "run market research on insurance.csv") beats the latest upload.
  const resolveTargetFile = useCallback(
    (question: string): UploadedFile | undefined => {
      const t = question.toLowerCase()
      return uploadedFiles.find(f => t.includes(f.name.toLowerCase())) ?? uploadedFiles[0]
    },
    [uploadedFiles]
  )

  // Runs a feature pipeline and patches the placeholder message with the result.
  // Used by both the quick-action cards and typed messages in feature mode.
  const executeFeature = useCallback(
    async (
      feature: Exclude<FeatureId, 'causal_analysis'>,
      localChatId: string,
      streamId: string,
      question: string,
      opts: { forceAnalyze?: boolean } = {}
    ) => {
      const fail = (msg: string) =>
        patchMessage(localChatId, streamId, {
          streaming: false,
          content: `**Something went wrong.** ${msg}`,
        })

      const file = resolveTargetFile(question)
      const edaSession = edaSessions.current.get(localChatId)
      if (!file && !(feature === 'eda' && edaSession)) {
        patchMessage(localChatId, streamId, {
          streaming: false,
          content: 'Please **upload a dataset first** (CSV or Excel) — then run this analysis again.',
        })
        setIsLoading(false)
        return
      }

      try {
        if (feature === 'eda') {
          if (edaSession && !opts.forceAnalyze) {
            // Existing session → treat the message as a follow-up question.
            const res = await fetch(`${API}/eda/ask`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ session_id: edaSession, question }),
            })
            const data = await res.json()
            if (!res.ok || data.ok === false) fail(data.error ?? `HTTP ${res.status}`)
            else patchMessage(localChatId, streamId, { streaming: false, kind: 'eda', data, content: 'EDA follow-up' })
          } else {
            const res = await fetch(`${API}/eda/analyze`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ session_id: localChatId, file_id: file!.id }),
            })
            const data = await res.json()
            if (!res.ok || data.ok === false) {
              fail(data.error ?? data.message ?? `EDA failed (HTTP ${res.status})`)
            } else {
              edaSessions.current.set(localChatId, localChatId)
              patchMessage(localChatId, streamId, { streaming: false, kind: 'eda', data, content: 'EDA complete' })
            }
          }
        } else if (feature === 'market_research') {
          const res = await fetch(`${API}/market-research/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: file!.id }),
          })
          const data = await res.json()
          if (!res.ok) {
            fail(data.message ?? `Market research failed (HTTP ${res.status})`)
          } else {
            patchMessage(localChatId, streamId, {
              streaming: false,
              kind: 'market_research',
              data,
              content: 'Market research complete',
            })
          }
        } else if (feature === 'insight_builder') {
          const blobRes = await fetch(`${API}/files/${file!.id}/download`)
          if (!blobRes.ok) return fail(`Could not read the uploaded file (HTTP ${blobRes.status}).`)
          const blob = await blobRes.blob()
          const form = new FormData()
          form.append('file', new File([blob], file!.name))
          const sessRes = await fetch(`${API}/insight/datasets`, { method: 'POST', body: form })
          const sess = await sessRes.json()
          if (!sessRes.ok) return fail(sess.detail ?? `Insight session failed (HTTP ${sessRes.status})`)

          patchMessage(localChatId, streamId, {
            content:
              '_Insight Builder pipeline is running — a full run typically takes **30–40 minutes**. Leave this tab open…_',
          })
          const res = await fetch(`${API}/insight/datasets/${sess.session_id}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
          })
          const data = await res.json()
          if (!res.ok) {
            fail(data.detail ?? `Insight pipeline failed (HTTP ${res.status})`)
          } else {
            patchMessage(localChatId, streamId, {
              streaming: false,
              kind: 'insights',
              data,
              content: 'Insight Builder complete',
            })
          }
        }
      } catch (err) {
        fail(`Backend not reachable — is the FastAPI server running on port 8001? (${(err as Error).message})`)
      } finally {
        setIsLoading(false)
      }
    },
    [patchMessage, resolveTargetFile]
  )

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

      // Feature routing: an active mode chip (EDA / Market Research) or an
      // explicit feature request in the text goes to the real pipeline —
      // never to the plain chat LLM (which mocks without an Anthropic key).
      const feature: FeatureId | null = modes.includes('market_research')
        ? 'market_research'
        : modes.includes('eda')
          ? 'eda'
          : detectFeature(content)
      if (feature && feature !== 'causal_analysis') {
        await executeFeature(feature, localChatId, streamId, content.trim())
        return
      }

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
    [activeChatId, isLoading, uploadedFiles, executeFeature]
  )

  // ── Feature runs (EDA / Market Research / Insight Builder) ────────────────
  const runFeature = useCallback(
    async (feature: FeatureId) => {
      if (isLoading) return
      const localChatId = activeChatId
      const latestFile = uploadedFiles[0]

      if (feature === 'causal_analysis') {
        appendMessages(localChatId, [
          { id: genId(), role: 'user', content: 'Run Causal Analysis', timestamp: new Date() },
          {
            id: genId(),
            role: 'assistant',
            content:
              '**Causal Analysis — coming soon.** This will chain EDA, Market Research and the Insight Builder into one end-to-end causal pipeline. For now, try the individual features.',
            timestamp: new Date(),
          },
        ])
        return
      }

      if (!latestFile) {
        appendMessages(localChatId, [
          {
            id: genId(),
            role: 'assistant',
            content: 'Please **upload a dataset first** (CSV or Excel) — then run this analysis again.',
            timestamp: new Date(),
          },
        ])
        return
      }

      const labels: Record<string, string> = {
        eda: `Run EDA on ${latestFile.name}`,
        market_research: `Run market research on ${latestFile.name}`,
        insight_builder: `Build validated insights from ${latestFile.name}`,
      }
      const streamId = `stream-${genId()}`
      appendMessages(localChatId, [
        { id: genId(), role: 'user', content: labels[feature], timestamp: new Date() },
        { id: streamId, role: 'assistant', content: '', timestamp: new Date(), streaming: true },
      ])
      setIsLoading(true)
      // Card click always (re)runs the full analysis, even if a session exists.
      await executeFeature(feature, localChatId, streamId, labels[feature], { forceAnalyze: true })
    },
    [activeChatId, isLoading, uploadedFiles, appendMessages, executeFeature]
  )

  // Follow-up question against an existing EDA session (from suggestion chips).
  const sendEdaFollowup = useCallback(
    async (question: string) => {
      const localChatId = activeChatId
      if (!edaSessions.current.get(localChatId) || isLoading) return
      const streamId = `stream-${genId()}`
      appendMessages(localChatId, [
        { id: genId(), role: 'user', content: question, timestamp: new Date() },
        { id: streamId, role: 'assistant', content: '', timestamp: new Date(), streaming: true },
      ])
      setIsLoading(true)
      await executeFeature('eda', localChatId, streamId, question)
    },
    [activeChatId, isLoading, appendMessages, executeFeature]
  )

  // ── Chat management (rename / delete) ─────────────────────────────────────
  const renameChat = useCallback((id: string, title: string) => {
    const trimmed = title.trim()
    if (!trimmed) return
    setChats(prev => prev.map(c => (c.id === id ? { ...c, title: trimmed } : c)))
    const backendId = backendIds.current.get(id)
    if (backendId) {
      fetch(`${API}/chats/${backendId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: trimmed }),
      }).catch(() => {})
    }
  }, [])

  const deleteChat = useCallback(
    (id: string) => {
      // Keep updaters pure: compute the next state here, never call another
      // setState inside the setChats updater (React discards impure updaters).
      const remaining = chats.filter(c => c.id !== id)
      if (remaining.length === 0) {
        const localId = `local-${genId()}`
        setChats([{ id: localId, title: 'New Chat', messages: [], createdAt: new Date() }])
        setActiveChatId(localId)
      } else {
        setChats(remaining)
        if (id === activeChatId) setActiveChatId(remaining[0].id)
      }
      const backendId = backendIds.current.get(id)
      backendIds.current.delete(id)
      edaSessions.current.delete(id)
      if (backendId) {
        fetch(`${API}/chats/${backendId}`, { method: 'DELETE' }).catch(() => {})
      }
    },
    [chats, activeChatId]
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
    runFeature,
    sendEdaFollowup,
    newChat,
    renameChat,
    deleteChat,
    isLoading,
  }
}
