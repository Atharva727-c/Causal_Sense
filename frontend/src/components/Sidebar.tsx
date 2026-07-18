import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Chat } from '../types'

interface Props {
  chats: Chat[]
  activeChatId: string
  onSelectChat: (id: string) => void
  onNewChat: () => void
  onRenameChat: (id: string, title: string) => void
  onDeleteChat: (id: string) => void
}

function timeAgo(date: Date) {
  const diff = Date.now() - date.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

const NAV_ITEMS = [
  {
    label: 'Notebooks',
    icon: (
      <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2.5" y="2.5" width="15" height="15" rx="2.5"/>
        <line x1="2.5" y1="8" x2="17.5" y2="8"/>
        <line x1="8" y1="17.5" x2="8" y2="8"/>
      </svg>
    ),
  },
  {
    label: 'Datasets',
    icon: (
      <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <ellipse cx="10" cy="5.5" rx="6.5" ry="2.2"/>
        <path d="M16.5 10c0 1.22-2.91 2.2-6.5 2.2S3.5 11.22 3.5 10"/>
        <path d="M3.5 5.5v9C3.5 15.72 6.41 16.7 10 16.7s6.5-.98 6.5-2.2v-9"/>
      </svg>
    ),
  },
]

function ChatRow({
  chat, isActive, idx, onSelect, onRename, onDelete,
}: {
  chat: Chat
  isActive: boolean
  idx: number
  onSelect: () => void
  onRename: (title: string) => void
  onDelete: () => void
}) {
  const [hovered, setHovered] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(chat.title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  const commit = () => {
    setEditing(false)
    if (draft.trim() && draft.trim() !== chat.title) onRename(draft.trim())
    else setDraft(chat.title)
  }

  return (
    <motion.div
      role="button"
      tabIndex={0}
      onClick={() => !editing && onSelect()}
      onKeyDown={e => e.key === 'Enter' && !editing && onSelect()}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      transition={{ delay: idx * 0.04, type: 'spring', stiffness: 320, damping: 26 }}
      whileHover={!isActive ? { backgroundColor: 'rgba(255,255,255,0.04)' } : {}}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 12px', borderRadius: 9, marginBottom: 2, cursor: 'pointer',
        background: isActive ? 'rgba(124,58,237,0.16)' : 'transparent',
        borderLeft: `2px solid ${isActive ? '#9B7EFF' : 'transparent'}`,
        paddingLeft: isActive ? 10 : 12,
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        {editing ? (
          <input
            ref={inputRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={e => {
              e.stopPropagation()
              if (e.key === 'Enter') commit()
              if (e.key === 'Escape') { setDraft(chat.title); setEditing(false) }
            }}
            onClick={e => e.stopPropagation()}
            style={{
              width: '100%', fontSize: 12.5, fontWeight: 500,
              color: '#c4b5fd', background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(155,126,255,0.4)', borderRadius: 6,
              padding: '2px 6px', outline: 'none', marginBottom: 2,
            }}
          />
        ) : (
          <p style={{
            fontSize: 12.5, fontWeight: isActive ? 500 : 400,
            color: isActive ? '#c4b5fd' : 'rgba(255,255,255,0.65)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            marginBottom: 2,
          }}>
            {chat.title}
          </p>
        )}
        <p style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.2)' }}>
          {timeAgo(chat.createdAt)}
        </p>
      </div>
      {(hovered || isActive) && !editing && (
        <span style={{ display: 'flex', gap: 2, marginLeft: 6, flexShrink: 0 }}>
          <button
            title="Rename chat"
            onClick={e => { e.stopPropagation(); setDraft(chat.title); setEditing(true) }}
            style={{
              width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
              borderRadius: 5, border: 'none', background: 'transparent', cursor: 'pointer',
              color: 'rgba(255,255,255,0.4)',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = '#c4b5fd' }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.4)' }}
          >
            <svg width="11" height="11" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 3l3 3L7 16H4v-3L14 3z"/>
            </svg>
          </button>
          <button
            title="Delete chat"
            onClick={e => { e.stopPropagation(); onDelete() }}
            style={{
              width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
              borderRadius: 5, border: 'none', background: 'transparent', cursor: 'pointer',
              color: 'rgba(255,255,255,0.4)',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = '#f87171' }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.4)' }}
          >
            <svg width="11" height="11" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h14M8 6V4h4v2M5 6l1 11h8l1-11M8.5 9v5M11.5 9v5"/>
            </svg>
          </button>
        </span>
      )}
    </motion.div>
  )
}

export default function Sidebar({ chats, activeChatId, onSelectChat, onNewChat, onRenameChat, onDeleteChat }: Props) {
  return (
    <aside
      style={{
        width: 268,
        minWidth: 268,
        background: '#09081a',
        borderRight: '1px solid rgba(255,255,255,0.05)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* ── Logo ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '18px 20px 16px',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #7C3AED 0%, #6B4EFF 60%, #9B7EFF 100%)',
              boxShadow: '0 0 16px rgba(124,58,237,0.45)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
              <circle cx="4" cy="4" r="1.7" fill="white" fillOpacity="0.95"/>
              <circle cx="16" cy="4" r="1.7" fill="white" fillOpacity="0.95"/>
              <circle cx="4" cy="16" r="1.7" fill="white" fillOpacity="0.95"/>
              <circle cx="16" cy="16" r="1.7" fill="white" fillOpacity="0.95"/>
              <circle cx="10" cy="10" r="2.2" fill="white"/>
              <line x1="4" y1="4" x2="10" y2="10" stroke="white" strokeWidth="1" strokeOpacity="0.5"/>
              <line x1="16" y1="4" x2="10" y2="10" stroke="white" strokeWidth="1" strokeOpacity="0.5"/>
              <line x1="4" y1="16" x2="10" y2="10" stroke="white" strokeWidth="1" strokeOpacity="0.5"/>
              <line x1="16" y1="16" x2="10" y2="10" stroke="white" strokeWidth="1" strokeOpacity="0.5"/>
            </svg>
          </div>
          <span style={{ fontWeight: 600, fontSize: 14.5, letterSpacing: '-0.01em', color: '#f0edfc' }}>
            CausalSense
          </span>
        </div>
        <button
          style={{
            width: 28, height: 28, borderRadius: 8,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'rgba(255,255,255,0.22)', cursor: 'pointer', border: 'none',
            background: 'transparent', transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            const b = e.currentTarget
            b.style.background = 'rgba(255,255,255,0.07)'
            b.style.color = 'rgba(255,255,255,0.55)'
          }}
          onMouseLeave={e => {
            const b = e.currentTarget
            b.style.background = 'transparent'
            b.style.color = 'rgba(255,255,255,0.22)'
          }}
        >
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
            <rect x="2" y="2" width="16" height="16" rx="3"/>
            <line x1="7" y1="2" x2="7" y2="18"/>
          </svg>
        </button>
      </div>

      {/* ── New Chat ── */}
      <div style={{ padding: '14px 16px 12px', flexShrink: 0 }}>
        <button
          onClick={onNewChat}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 7, color: 'white', fontSize: 13, fontWeight: 600,
            padding: '9px 0', borderRadius: 10, border: 'none', cursor: 'pointer',
            background: 'linear-gradient(135deg, #7C3AED 0%, #6B4EFF 100%)',
            boxShadow: '0 2px 12px rgba(124,58,237,0.35), inset 0 1px 0 rgba(255,255,255,0.12)',
          }}
        >
          <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round">
            <line x1="10" y1="3" x2="10" y2="17"/>
            <line x1="3" y1="10" x2="17" y2="10"/>
          </svg>
          New Chat
        </button>
      </div>

      {/* ── History label ── */}
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '4px 20px 10px', flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.2)' }}>
          History
        </span>
        <button
          style={{
            width: 22, height: 22, borderRadius: 6, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            color: 'rgba(255,255,255,0.18)', border: 'none',
            background: 'transparent', cursor: 'pointer', transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            const b = e.currentTarget
            b.style.background = 'rgba(255,255,255,0.07)'
            b.style.color = 'rgba(255,255,255,0.48)'
          }}
          onMouseLeave={e => {
            const b = e.currentTarget
            b.style.background = 'transparent'
            b.style.color = 'rgba(255,255,255,0.18)'
          }}
        >
          <svg width="11" height="11" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="9" cy="9" r="5.5"/>
            <line x1="14" y1="14" x2="17.5" y2="17.5"/>
          </svg>
        </button>
      </div>

      {/* ── Chat list ── */}
      <div className="sidebar-scroll" style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
        <AnimatePresence initial={false}>
        {chats.map((chat, idx) => (
          <ChatRow
            key={chat.id}
            chat={chat}
            isActive={chat.id === activeChatId}
            idx={idx}
            onSelect={() => onSelectChat(chat.id)}
            onRename={title => onRenameChat(chat.id, title)}
            onDelete={() => onDeleteChat(chat.id)}
          />
        ))}
        </AnimatePresence>
      </div>

      {/* ── Bottom nav ── */}
      <div
        style={{
          padding: '10px 8px 6px',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          flexShrink: 0,
        }}
      >
        {NAV_ITEMS.map(item => (
          <button
            key={item.label}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 12px', borderRadius: 9, fontSize: 12.5, fontWeight: 500,
              color: 'rgba(255,255,255,0.32)', border: 'none', background: 'transparent',
              cursor: 'pointer', textAlign: 'left', transition: 'all 0.14s', marginBottom: 2,
            }}
            onMouseEnter={e => {
              const b = e.currentTarget
              b.style.background = 'rgba(255,255,255,0.05)'
              b.style.color = 'rgba(255,255,255,0.68)'
            }}
            onMouseLeave={e => {
              const b = e.currentTarget
              b.style.background = 'transparent'
              b.style.color = 'rgba(255,255,255,0.32)'
            }}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </div>

      {/* ── User profile ── */}
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px 14px',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 30, height: 30, borderRadius: '50%',
            background: 'linear-gradient(135deg, #7C3AED, #9B7EFF)',
            boxShadow: '0 0 10px rgba(124,58,237,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'white', fontSize: 11.5, fontWeight: 700, flexShrink: 0,
          }}
        >
          S
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 12.5, fontWeight: 600, color: 'rgba(255,255,255,0.82)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            Sahil
          </p>
          <p style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.25)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            sahil@causalsense.ai
          </p>
        </div>
        <button
          style={{
            width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'rgba(255,255,255,0.2)', flexShrink: 0, border: 'none',
            background: 'transparent', cursor: 'pointer', transition: 'color 0.14s',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.5)' }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.2)' }}
        >
          <svg width="11" height="11" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <polyline points="7 15 13 10 7 5"/>
          </svg>
        </button>
      </div>
    </aside>
  )
}
