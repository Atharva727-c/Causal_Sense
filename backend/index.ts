import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import morgan from 'morgan'
import rateLimit from 'express-rate-limit'
import chatsRouter from './routes/chats'
import filesRouter from './routes/files'

const app = express()
const PORT = process.env.PORT || 3001

// ── Security & logging ──────────────────────────────────────────────────────
app.use(helmet({ contentSecurityPolicy: false }))
app.use(morgan('dev'))

app.use(cors({
  origin: process.env.FRONTEND_ORIGIN ?? 'http://localhost:5173',
  methods: ['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}))

// Rate limiting — 200 req / 15min per IP for API, stricter for message streaming
app.use('/api', rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 200,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many requests, please try again later.' },
}))

app.use('/api/chats/:id/messages', rateLimit({
  windowMs: 60 * 1000,
  max: 20,
  message: { error: 'Message rate limit reached, slow down a bit.' },
}))

// ── Body parsing ────────────────────────────────────────────────────────────
app.use(express.json({ limit: '2mb' }))
app.use(express.urlencoded({ extended: true }))

// ── Routes ──────────────────────────────────────────────────────────────────
app.use('/api/chats', chatsRouter)
app.use('/api/files', filesRouter)

app.get('/health', (_, res) => {
  res.json({ status: 'ok', mode: process.env.ANTHROPIC_API_KEY ? 'live' : 'mock', ts: Date.now() })
})

// ── Global error handler ────────────────────────────────────────────────────
app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error('Unhandled error:', err)
  const status = err.status ?? err.statusCode ?? 500
  res.status(status).json({ error: err.message ?? 'Internal server error' })
})

app.listen(PORT, () => {
  const hasKey = !!process.env.ANTHROPIC_API_KEY
  console.log(`\n🚀 CausalSense backend  →  http://localhost:${PORT}`)
  console.log(`   Mode: ${hasKey ? '✓ Claude AI (live)' : '⚡ Mock responses (set ANTHROPIC_API_KEY for live)'}`)
  console.log(`   DB:   SQLite WAL\n`)
})
