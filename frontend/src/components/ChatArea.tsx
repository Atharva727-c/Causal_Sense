import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Chat, ActiveMode, FeatureId } from '../types'
import ChatMessage from './ChatMessage'
import QuickActions from './QuickActions'
import MessageInput from './MessageInput'

interface Props {
  chat: Chat
  chatTitle: string
  isLoading: boolean
  onSend: (message: string, modes: ActiveMode[]) => void
  onUpload: (file: File) => void
  onFeature: (feature: FeatureId) => void
  onFollowup: (question: string) => void
}

function TypingDots() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      {[0, 1, 2].map(i => (
        <motion.span
          key={i}
          style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', display: 'inline-block' }}
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.7, 1.1, 0.7] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.16, ease: 'easeInOut' }}
        />
      ))}
    </div>
  )
}

export default function ChatArea({ chat, chatTitle, isLoading, onSend, onUpload, onFeature, onFollowup }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  const [inWelcome, setInWelcome] = useState(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat.messages, isLoading])

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }

  const isStreaming = chat.messages.some(m => m.streaming)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0, height: '100%', background: '#f7f6fb' }}>

      {/* ── Top bar ── */}
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 20px', height: 56, flexShrink: 0,
          background: 'white',
          borderBottom: '1px solid #eeecf8',
          boxShadow: '0 1px 8px rgba(0,0,0,0.035)',
        }}
      >
        <motion.button
          whileHover={{ color: '#7C3AED', backgroundColor: '#f5f3ff' }}
          whileTap={{ scale: 0.98 }}
          transition={{ duration: 0.14 }}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            fontSize: 13.5, fontWeight: 600, color: '#0f0a1e',
            padding: '5px 8px', borderRadius: 8, border: 'none',
            background: 'transparent', cursor: 'pointer',
            maxWidth: 340,
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {chatTitle}
          </span>
          <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}>
            <polyline points="5 8 10 13 15 8"/>
          </svg>
        </motion.button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          {[
            {
              label: 'Share',
              icon: (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                </svg>
              ),
            },
            {
              label: 'Your Data',
              icon: (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <ellipse cx="12" cy="5" rx="9" ry="3"/>
                  <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
                  <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
                </svg>
              ),
            },
          ].map(btn => (
            <motion.button
              key={btn.label}
              whileHover={{ backgroundColor: '#f3f4f6', color: '#111827' }}
              whileTap={{ scale: 0.97 }}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '5px 10px', borderRadius: 8,
                fontSize: 12, fontWeight: 500, color: '#6b7280',
                border: 'none', background: 'transparent', cursor: 'pointer',
              }}
            >
              {btn.icon}
              {btn.label}
            </motion.button>
          ))}

          <motion.button
            whileHover={{ backgroundColor: '#f3f4f6', color: '#6b7280' }}
            whileTap={{ scale: 0.95 }}
            style={{
              width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
              borderRadius: 8, color: '#9ca3af', border: 'none', background: 'transparent', cursor: 'pointer',
            }}
          >
            <svg width="14" height="4" viewBox="0 0 20 6" fill="currentColor">
              <circle cx="2.5" cy="3" r="2"/><circle cx="10" cy="3" r="2"/><circle cx="17.5" cy="3" r="2"/>
            </svg>
          </motion.button>

          <div style={{ width: 1, height: 18, background: '#e5e7eb', margin: '0 4px' }}/>

          <motion.button
            whileHover={{ boxShadow: '0 4px 16px rgba(124,58,237,0.42)', y: -1 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => document.querySelector<HTMLInputElement>('input[type="file"]')?.click()}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '6px 14px', borderRadius: 9,
              fontSize: 12, fontWeight: 600, color: 'white',
              border: 'none', cursor: 'pointer',
              background: 'linear-gradient(135deg, #7C3AED 0%, #6B4EFF 100%)',
              boxShadow: '0 2px 8px rgba(124,58,237,0.28)',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
              <path d="M3 19v1a2 2 0 002 2h14a2 2 0 002-2v-1"/>
            </svg>
            Upload
          </motion.button>
        </div>
      </div>

      {/* ── Chat body ── */}
      <div
        className="light-scroll"
        style={{ flex: 1, overflowY: 'auto', position: 'relative' }}
        onMouseMove={chat.messages.length === 0 ? handleMouseMove : undefined}
        onMouseEnter={() => setInWelcome(chat.messages.length === 0)}
        onMouseLeave={() => setInWelcome(false)}
      >
        {/* Plain conditional render — AnimatePresence mode="wait" could wedge
            here (welcome faded to opacity 0 but never unmounted under
            StrictMode, so the message list never appeared). */}
        {chat.messages.length === 0 ? (
            <motion.div
              key="welcome"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', height: '100%', padding: '40px 32px',
                position: 'relative', overflow: 'hidden',
              }}
            >
              {/* Mouse-tracking spotlight */}
              {inWelcome && (
                <motion.div
                  style={{
                    position: 'absolute', width: 640, height: 640, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(124,58,237,0.055) 0%, transparent 70%)',
                    pointerEvents: 'none',
                    x: mousePos.x - 320, y: mousePos.y - 320,
                  }}
                  animate={{ x: mousePos.x - 320, y: mousePos.y - 320 }}
                  transition={{ type: 'spring', stiffness: 110, damping: 18, mass: 0.4 }}
                />
              )}

              {/* Ambient blobs */}
              <div style={{ position: 'absolute', top: '12%', left: '18%', width: 340, height: 340, borderRadius: '50%', background: 'rgba(124,58,237,0.035)', filter: 'blur(90px)', pointerEvents: 'none' }}/>
              <div style={{ position: 'absolute', bottom: '18%', right: '14%', width: 280, height: 280, borderRadius: '50%', background: 'rgba(107,78,255,0.035)', filter: 'blur(80px)', pointerEvents: 'none' }}/>

              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, marginBottom: 40, position: 'relative' }}>
                <motion.div
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 22, delay: 0.04 }}
                  style={{
                    width: 76, height: 76, borderRadius: 24,
                    background: 'linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)',
                    boxShadow: '0 10px 32px rgba(124,58,237,0.16), 0 2px 8px rgba(124,58,237,0.08)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    marginBottom: 14,
                  }}
                >
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                    <circle cx="5" cy="5" r="2" fill="#7C3AED" fillOpacity="0.85"/>
                    <circle cx="19" cy="5" r="2" fill="#7C3AED" fillOpacity="0.85"/>
                    <circle cx="5" cy="19" r="2" fill="#7C3AED" fillOpacity="0.85"/>
                    <circle cx="19" cy="19" r="2" fill="#7C3AED" fillOpacity="0.85"/>
                    <circle cx="12" cy="12" r="2.8" fill="#7C3AED"/>
                    <line x1="5" y1="5" x2="12" y2="12" stroke="#7C3AED" strokeWidth="1.2" strokeOpacity="0.4"/>
                    <line x1="19" y1="5" x2="12" y2="12" stroke="#7C3AED" strokeWidth="1.2" strokeOpacity="0.4"/>
                    <line x1="5" y1="19" x2="12" y2="12" stroke="#7C3AED" strokeWidth="1.2" strokeOpacity="0.4"/>
                    <line x1="19" y1="19" x2="12" y2="12" stroke="#7C3AED" strokeWidth="1.2" strokeOpacity="0.4"/>
                    <circle cx="19.5" cy="4.5" r="3.5" fill="#7C3AED"/>
                    <path d="M18 4.5h3M19.5 3v3" stroke="white" strokeWidth="1.4" strokeLinecap="round"/>
                  </svg>
                </motion.div>

                <motion.h1
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.09, duration: 0.38 }}
                  style={{ fontSize: 23, fontWeight: 700, color: '#0f0a1e', letterSpacing: '-0.025em', textAlign: 'center' }}
                >
                  How can I help you today?
                </motion.h1>

                <motion.div
                  initial={{ width: 0, opacity: 0 }}
                  animate={{ width: '100%', opacity: 1 }}
                  transition={{ delay: 0.28, duration: 0.55 }}
                  style={{ height: 1, background: 'linear-gradient(90deg, transparent, rgba(124,58,237,0.18), transparent)', margin: '4px auto', maxWidth: 340 }}
                />

                <motion.p
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.16, duration: 0.38 }}
                  style={{ fontSize: 13.5, color: '#9ca3af', fontWeight: 400, textAlign: 'center', maxWidth: 400, lineHeight: 1.6 }}
                >
                  Upload market data, run deep analysis, or generate probabilistic forecasts.
                </motion.p>
              </div>

              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.38 }}
              >
                <QuickActions onFeature={onFeature} />
              </motion.div>
            </motion.div>
          ) : (
            <motion.div
              key="messages"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ padding: '28px 28px 8px', maxWidth: 860, margin: '0 auto', width: '100%' }}
            >
              {chat.messages.map(msg => (
                <ChatMessage key={msg.id} message={msg} onFollowup={onFollowup} />
              ))}

              <AnimatePresence>
                {isLoading && !isStreaming && (
                  <motion.div
                    key="typing"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    transition={{ type: 'spring', stiffness: 300, damping: 26 }}
                    style={{ display: 'flex', gap: 12, marginBottom: 20 }}
                  >
                    <div style={{
                      width: 30, height: 30, borderRadius: 10, flexShrink: 0,
                      background: 'linear-gradient(135deg, #f0eeff, #e5deff)',
                      boxShadow: '0 2px 8px rgba(124,58,237,0.1)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                        <circle cx="4" cy="4" r="1.8" fill="#7C3AED"/>
                        <circle cx="16" cy="4" r="1.8" fill="#7C3AED"/>
                        <circle cx="4" cy="16" r="1.8" fill="#7C3AED"/>
                        <circle cx="16" cy="16" r="1.8" fill="#7C3AED"/>
                        <circle cx="10" cy="10" r="2.2" fill="#7C3AED"/>
                      </svg>
                    </div>
                    <div style={{
                      display: 'flex', alignItems: 'center',
                      padding: '10px 14px', borderRadius: '4px 16px 16px 16px',
                      background: 'white', border: '1px solid #eeecf8',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                    }}>
                      <TypingDots />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
              <div ref={bottomRef} />
            </motion.div>
          )}
      </div>

      {/* ── Input ── */}
      <div style={{ flexShrink: 0, background: '#f7f6fb' }}>
        <MessageInput key={chat.id} onSend={onSend} onUpload={onUpload} isLoading={isLoading} />
      </div>
    </div>
  )
}
