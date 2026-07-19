import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message } from '../types'
import MarketResearchResult, { type MarketResearchData } from './results/MarketResearchResult'
import EdaResult, { type EdaData } from './results/EdaResult'
import InsightsResult, { type InsightsData } from './results/InsightsResult'
import CausalResult, { type CausalData } from './results/CausalResult'

interface Props {
  message: Message
  onFollowup?: (question: string) => void
}

export default function ChatMessage({ message, onFollowup }: Props) {
  if (message.role === 'user') {
    return (
      <motion.div
        style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20 }}
        initial={{ opacity: 0, y: 10, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: 'spring', stiffness: 420, damping: 32 }}
      >
        <div
          style={{
            maxWidth: '68%',
            borderRadius: '18px 4px 18px 18px',
            padding: '11px 16px',
            background: 'linear-gradient(135deg, #7C3AED 0%, #6B4EFF 100%)',
            boxShadow: '0 3px 16px rgba(124,58,237,0.22)',
          }}
        >
          <p style={{ fontSize: 13.5, color: 'white', lineHeight: 1.65, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {message.content}
          </p>
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      style={{ display: 'flex', gap: 12, marginBottom: 24 }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 360, damping: 28 }}
    >
      {/* Avatar */}
      <div
        style={{
          width: 30, height: 30, borderRadius: 10, flexShrink: 0, marginTop: 3,
          background: 'linear-gradient(135deg, #f0eeff 0%, #e5deff 100%)',
          boxShadow: '0 2px 8px rgba(124,58,237,0.1)',
          border: '1px solid rgba(124,58,237,0.12)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
          <circle cx="4" cy="4" r="1.6" fill="#7C3AED"/>
          <circle cx="16" cy="4" r="1.6" fill="#7C3AED"/>
          <circle cx="4" cy="16" r="1.6" fill="#7C3AED"/>
          <circle cx="16" cy="16" r="1.6" fill="#7C3AED"/>
          <circle cx="10" cy="10" r="2" fill="#7C3AED"/>
          <line x1="4" y1="4" x2="10" y2="10" stroke="#7C3AED" strokeWidth="1" strokeOpacity="0.38"/>
          <line x1="16" y1="4" x2="10" y2="10" stroke="#7C3AED" strokeWidth="1" strokeOpacity="0.38"/>
          <line x1="4" y1="16" x2="10" y2="10" stroke="#7C3AED" strokeWidth="1" strokeOpacity="0.38"/>
          <line x1="16" y1="16" x2="10" y2="10" stroke="#7C3AED" strokeWidth="1" strokeOpacity="0.38"/>
        </svg>
      </div>

      {/* Bubble */}
      <div
        style={{
          flex: 1, minWidth: 0,
          borderRadius: '4px 18px 18px 18px',
          padding: '14px 18px',
          background: 'white',
          border: '1px solid #eeecf8',
          boxShadow: '0 2px 10px rgba(0,0,0,0.04)',
          position: 'relative',
        }}
      >
        {message.kind === 'market_research' && message.data ? (
          <MarketResearchResult data={message.data as MarketResearchData} />
        ) : message.kind === 'eda' && message.data ? (
          <EdaResult data={message.data as EdaData} onFollowup={onFollowup} />
        ) : message.kind === 'insights' && message.data ? (
          <InsightsResult data={message.data as InsightsData} />
        ) : message.kind === 'causal' && message.data ? (
          <CausalResult data={message.data as CausalData} />
        ) : message.content.length > 0 ? (
          <div className="prose max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            {message.streaming && <span className="streaming-cursor" />}
          </div>
        ) : (
          /* Empty streaming state — show pulsing dots */
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '2px 0' }}>
            {[0, 1, 2].map(i => (
              <motion.span
                key={i}
                style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', display: 'inline-block' }}
                animate={{ opacity: [0.3, 1, 0.3], scale: [0.7, 1.1, 0.7] }}
                transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.16, ease: 'easeInOut' }}
              />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}
