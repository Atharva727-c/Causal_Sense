import { useState, useRef, useCallback, useEffect, type KeyboardEvent, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ActiveMode } from '../types'

// ── localStorage history ────────────────────────────────────────────────────
const STORAGE_KEY = 'cs_attach_history'
const MAX_RECENT  = 5

interface RecentItem {
  id: string
  label: string
  action: string
  usedAt: number
}

function loadHistory(): RecentItem[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') } catch { return [] }
}
function saveHistory(items: RecentItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_RECENT)))
}
function timeAgo(ts: number) {
  const d = Date.now() - ts, m = Math.floor(d / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// ── Dropdown sections config ─────────────────────────────────────────────────
interface DropdownItem {
  id: string
  label: string
  desc: string
  action: string
  available: boolean
  iconBg: string
  iconColor: string
  icon: ReactNode
}
interface Section { id: string; label: string; items: DropdownItem[] }

const ATTACH_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
  </svg>
)
const EDA_ICON = (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="currentColor">
    <rect x="0.5" y="7.5" width="3" height="6" rx="0.6"/>
    <rect x="5" y="4.5" width="3" height="9" rx="0.6"/>
    <rect x="9.5" y="1.5" width="3" height="12" rx="0.6"/>
  </svg>
)
const MR_ICON = (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="7" cy="7" r="5.5"/>
    <path d="M7 1.5c0 0-2.2 2.2-2.2 5.5S7 12.5 7 12.5M7 1.5c0 0 2.2 2.2 2.2 5.5S7 12.5 7 12.5"/>
    <line x1="1.5" y1="7" x2="12.5" y2="7"/>
  </svg>
)
const FORECAST_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
  </svg>
)
const MCP_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="5" r="3"/><circle cx="19" cy="19" r="3"/><circle cx="5" cy="19" r="3"/>
    <line x1="12" y1="8" x2="12" y2="14"/><line x1="12" y1="14" x2="19" y2="16"/>
    <line x1="12" y1="14" x2="5" y2="16"/>
  </svg>
)
const DB_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <ellipse cx="12" cy="5" rx="9" ry="3"/>
    <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
    <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
  </svg>
)
const RESEARCH_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="11" cy="11" r="8"/>
    <line x1="21" y1="21" x2="16.65" y2="16.65"/>
    <line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>
  </svg>
)
const NOTEBOOK_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
    <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
  </svg>
)

const SECTIONS: Section[] = [
  {
    id: 'files', label: 'Attach',
    items: [{
      id: 'attach_file', label: 'File', desc: 'CSV · Excel · JSON · Parquet · SQL',
      action: 'upload', available: true,
      iconBg: 'rgba(107,114,128,0.09)', iconColor: '#6b7280', icon: ATTACH_ICON,
    }],
  },
  {
    id: 'skills', label: 'Skills',
    items: [
      {
        id: 'skill_eda', label: 'EDA Agent', desc: 'Statistical analysis & data quality',
        action: 'mode_eda', available: true,
        iconBg: 'rgba(79,70,229,0.09)', iconColor: '#4f46e5', icon: EDA_ICON,
      },
      {
        id: 'skill_market_research', label: 'Market Research', desc: 'Competitive intelligence & scenarios',
        action: 'mode_market_research', available: true,
        iconBg: 'rgba(13,148,136,0.09)', iconColor: '#0d9488', icon: MR_ICON,
      },
      {
        id: 'skill_forecast', label: 'Forecasting', desc: 'Predictive scenario modelling',
        action: 'coming_soon', available: false,
        iconBg: 'rgba(236,72,153,0.07)', iconColor: '#db2777', icon: FORECAST_ICON,
      },
    ],
  },
  {
    id: 'integrations', label: 'Integrations',
    items: [
      {
        id: 'mcp_server', label: 'MCP Server', desc: 'Model Context Protocol tools',
        action: 'coming_soon', available: false,
        iconBg: 'rgba(59,130,246,0.09)', iconColor: '#3b82f6', icon: MCP_ICON,
      },
      {
        id: 'database', label: 'Database', desc: 'Query live databases directly',
        action: 'coming_soon', available: false,
        iconBg: 'rgba(245,158,11,0.09)', iconColor: '#d97706', icon: DB_ICON,
      },
    ],
  },
  {
    id: 'advanced', label: 'Advanced',
    items: [
      {
        id: 'deep_research', label: 'Deep Research', desc: 'Multi-source web investigation',
        action: 'coming_soon', available: false,
        iconBg: 'rgba(124,58,237,0.09)', iconColor: '#7c3aed', icon: RESEARCH_ICON,
      },
      {
        id: 'notebook', label: 'Notebook', desc: 'Export to analysis notebook',
        action: 'coming_soon', available: false,
        iconBg: 'rgba(20,184,166,0.09)', iconColor: '#0d9488', icon: NOTEBOOK_ICON,
      },
    ],
  },
]

// ── Mode config ──────────────────────────────────────────────────────────────
const MODE_CONFIG: Record<ActiveMode, {
  label: string; gradient: string; shadow: string; color: string
  bg: string; ring: string; focusBorder: string
  bannerBg: string; bannerBorder: string; tooltip: string; icon: ReactNode
}> = {
  eda: {
    label: 'EDA',
    gradient: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
    shadow: '0 2px 10px rgba(79,70,229,0.30)',
    color: '#4f46e5',
    bg: 'rgba(79,70,229,0.07)',
    ring: 'rgba(99,102,241,0.10)',
    focusBorder: '#6366f1',
    bannerBg: 'linear-gradient(90deg, rgba(79,70,229,0.06) 0%, transparent 100%)',
    bannerBorder: 'rgba(99,102,241,0.13)',
    tooltip: 'EDA mode — deep statistical analysis',
    icon: EDA_ICON,
  },
  market_research: {
    label: 'Market Research',
    gradient: 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)',
    shadow: '0 2px 10px rgba(13,148,136,0.30)',
    color: '#0d9488',
    bg: 'rgba(13,148,136,0.07)',
    ring: 'rgba(13,148,136,0.10)',
    focusBorder: '#0d9488',
    bannerBg: 'linear-gradient(90deg, rgba(13,148,136,0.06) 0%, transparent 100%)',
    bannerBorder: 'rgba(13,148,136,0.13)',
    tooltip: 'Market Research mode — competitive intelligence & scenarios',
    icon: MR_ICON,
  },
}

// Ordered list so banner/chips render consistently
const MODE_ORDER: ActiveMode[] = ['eda', 'market_research']

// ── Auto-resize hook ─────────────────────────────────────────────────────────
function useAutoResize(minH: number, maxH: number) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const adjust = useCallback((reset?: boolean) => {
    const el = ref.current; if (!el) return
    if (reset) { el.style.height = `${minH}px`; return }
    el.style.height = `${minH}px`
    el.style.height = Math.min(el.scrollHeight, maxH) + 'px'
  }, [minH, maxH])
  useEffect(() => { if (ref.current) ref.current.style.height = `${minH}px` }, [minH])
  return { ref, adjust }
}

// ── Props ────────────────────────────────────────────────────────────────────
interface Props {
  onSend: (message: string, modes: ActiveMode[]) => void
  onUpload: (file: File) => void
  isLoading: boolean
}

// ── Component ────────────────────────────────────────────────────────────────
export default function MessageInput({ onSend, onUpload, isLoading }: Props) {
  const [text, setText]                         = useState('')
  const [focused, setFocused]                   = useState(false)
  const [activeModes, setActiveModes]           = useState<Set<ActiveMode>>(new Set())
  const [isDropdownOpen, setIsDropdownOpen]     = useState(false)
  const [hoveredItem, setHoveredItem]           = useState<string | null>(null)
  const [recentItems, setRecentItems]           = useState<RecentItem[]>(loadHistory)

  const fileRef       = useRef<HTMLInputElement>(null)
  const dropdownRef   = useRef<HTMLDivElement>(null)
  const attachBtnRef  = useRef<HTMLButtonElement>(null)
  const { ref: textareaRef, adjust } = useAutoResize(52, 160)

  // Toggle a mode on/off
  const toggleMode = useCallback((m: ActiveMode) => {
    setActiveModes(prev => {
      const next = new Set(prev)
      if (next.has(m)) next.delete(m)
      else next.add(m)
      return next
    })
  }, [])

  // Close dropdown on outside click / ESC
  useEffect(() => {
    if (!isDropdownOpen) return
    const onDown = (e: MouseEvent) => {
      if (
        !dropdownRef.current?.contains(e.target as Node) &&
        !attachBtnRef.current?.contains(e.target as Node)
      ) setIsDropdownOpen(false)
    }
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') setIsDropdownOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [isDropdownOpen])

  // Add item to localStorage history
  const addToHistory = (item: DropdownItem) => {
    const entry: RecentItem = { id: item.id, label: item.label, action: item.action, usedAt: Date.now() }
    setRecentItems(prev => {
      const filtered = prev.filter(r => r.id !== item.id)
      const updated = [entry, ...filtered].slice(0, MAX_RECENT)
      saveHistory(updated)
      return updated
    })
  }

  // Handle dropdown item click
  const handleAction = (item: DropdownItem) => {
    setIsDropdownOpen(false)
    if (!item.available) return

    switch (item.action) {
      case 'upload':
        fileRef.current?.click()
        break
      case 'mode_eda':
        toggleMode('eda')
        addToHistory(item)
        break
      case 'mode_market_research':
        toggleMode('market_research')
        addToHistory(item)
        break
    }
  }

  const handleRecentClick = (recent: RecentItem) => {
    setIsDropdownOpen(false)
    switch (recent.action) {
      case 'upload':
        fileRef.current?.click()
        break
      case 'mode_eda':
        toggleMode('eda')
        break
      case 'mode_market_research':
        toggleMode('market_research')
        break
    }
  }

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed, [...activeModes])
    setText(''); adjust(true)
  }
  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  // Derived display values
  const activeModeList = MODE_ORDER.filter(m => activeModes.has(m))
  const primaryMode    = activeModeList[0] ?? null
  const primaryCfg     = primaryMode ? MODE_CONFIG[primaryMode] : null
  const focusBorder    = primaryCfg?.focusBorder ?? '#7C3AED'
  const focusRing      = primaryCfg?.ring ?? 'rgba(124,58,237,0.07)'

  const canSend = text.trim().length > 0 && !isLoading

  const placeholder =
    activeModes.size === 2 ? 'Analyse data with EDA and market intelligence…'
    : activeModes.has('eda') ? 'What do you want to explore in your data…'
    : activeModes.has('market_research') ? 'Describe the market or industry to research…'
    : 'Message CausalSense…'

  const sendGrad =
    activeModes.size === 2 ? 'linear-gradient(135deg, #4f46e5 0%, #0d9488 100%)'
    : activeModes.has('eda') ? 'linear-gradient(135deg,#4f46e5,#6366f1)'
    : activeModes.has('market_research') ? 'linear-gradient(135deg,#0d9488,#14b8a6)'
    : 'linear-gradient(135deg,#7C3AED,#6B4EFF)'

  const sendShadow =
    activeModes.has('eda') ? '0 2px 12px rgba(79,70,229,0.35)'
    : activeModes.has('market_research') ? '0 2px 12px rgba(13,148,136,0.35)'
    : '0 2px 12px rgba(124,58,237,0.32)'

  return (
    <div style={{ padding: '10px 20px 14px', position: 'relative' }}>

      {/* ── Attachment dropdown (rendered outside overflow:hidden card) ── */}
      <AnimatePresence>
        {isDropdownOpen && (
          <motion.div
            ref={dropdownRef}
            initial={{ opacity: 0, y: 10, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 420, damping: 30 }}
            style={{
              position: 'absolute',
              bottom: 'calc(100% + 4px)',
              left: 0,
              width: 272,
              background: 'white',
              borderRadius: 16,
              border: '1px solid #ece8fd',
              boxShadow: '0 16px 48px rgba(0,0,0,0.13), 0 4px 16px rgba(0,0,0,0.07)',
              zIndex: 200,
              overflow: 'hidden',
            }}
          >
            {/* Inner scroll area */}
            <div
              className="light-scroll"
              style={{ maxHeight: 388, overflowY: 'auto', padding: '6px 0 6px' }}
            >
              {/* Recent section */}
              {recentItems.length > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={{
                    padding: '6px 14px 4px',
                    fontSize: 9.5, fontWeight: 700, letterSpacing: '0.08em',
                    textTransform: 'uppercase', color: '#c4c4cc',
                  }}>
                    Recent
                  </div>
                  {recentItems.map(r => (
                    <button
                      key={r.id}
                      onClick={() => handleRecentClick(r)}
                      onMouseEnter={() => setHoveredItem(`recent-${r.id}`)}
                      onMouseLeave={() => setHoveredItem(null)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        width: '100%', padding: '7px 14px', border: 'none', cursor: 'pointer',
                        background: hoveredItem === `recent-${r.id}` ? '#faf8ff' : 'transparent',
                        transition: 'background 0.12s',
                        textAlign: 'left',
                      }}
                    >
                      <div style={{
                        width: 26, height: 26, borderRadius: 7, flexShrink: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: 'rgba(124,58,237,0.06)', color: '#a78bfa',
                      }}>
                        <svg width="11" height="11" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
                          <circle cx="10" cy="10" r="7.5"/>
                          <polyline points="10 6 10 10 13 12"/>
                        </svg>
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: 11.5, fontWeight: 600, color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {r.label}
                        </p>
                      </div>
                      <span style={{ fontSize: 10, color: '#c4c4cc', flexShrink: 0 }}>{timeAgo(r.usedAt)}</span>
                    </button>
                  ))}
                  <div style={{ height: 1, background: '#f3f0ff', margin: '6px 0' }} />
                </div>
              )}

              {/* Main sections */}
              {SECTIONS.map((section, si) => (
                <div key={section.id} style={{ marginBottom: si < SECTIONS.length - 1 ? 2 : 0 }}>
                  <div style={{
                    padding: '6px 14px 4px',
                    fontSize: 9.5, fontWeight: 700, letterSpacing: '0.08em',
                    textTransform: 'uppercase', color: '#c4c4cc',
                  }}>
                    {section.label}
                  </div>

                  {section.items.map(item => {
                    const hKey = `item-${item.id}`
                    const isActive = (item.action === 'mode_eda' && activeModes.has('eda')) ||
                                     (item.action === 'mode_market_research' && activeModes.has('market_research'))
                    return (
                      <button
                        key={item.id}
                        onClick={() => handleAction(item)}
                        onMouseEnter={() => setHoveredItem(hKey)}
                        onMouseLeave={() => setHoveredItem(null)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10,
                          width: '100%', padding: '8px 14px', border: 'none',
                          cursor: item.available ? 'pointer' : 'default',
                          background: hoveredItem === hKey && item.available ? '#faf8ff' : 'transparent',
                          transition: 'background 0.12s',
                          textAlign: 'left',
                          opacity: item.available ? 1 : 0.55,
                        }}
                      >
                        {/* Icon */}
                        <div style={{
                          width: 30, height: 30, borderRadius: 9, flexShrink: 0,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          background: isActive ? item.iconColor : item.iconBg,
                          color: isActive ? 'white' : item.iconColor,
                          transition: 'background 0.15s, color 0.15s',
                        }}>
                          {item.icon}
                        </div>

                        {/* Text */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontSize: 12, fontWeight: 600, color: '#111827', marginBottom: 1 }}>
                            {item.label}
                          </p>
                          <p style={{ fontSize: 10.5, color: '#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {item.desc}
                          </p>
                        </div>

                        {/* Right: active check OR coming-soon badge */}
                        <div style={{ flexShrink: 0 }}>
                          {isActive ? (
                            <div style={{
                              width: 18, height: 18, borderRadius: 99,
                              background: item.iconColor,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                              <svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
                                <polyline points="1.5 5 4 7.5 8.5 2"/>
                              </svg>
                            </div>
                          ) : !item.available ? (
                            <span style={{
                              fontSize: 9, fontWeight: 700, letterSpacing: '0.04em',
                              color: '#d97706', background: '#fffbeb',
                              border: '1px solid #fde68a',
                              borderRadius: 99, padding: '2px 6px',
                              textTransform: 'uppercase',
                            }}>
                              Soon
                            </span>
                          ) : null}
                        </div>
                      </button>
                    )
                  })}

                  {si < SECTIONS.length - 1 && (
                    <div style={{ height: 1, background: '#f5f3ff', margin: '6px 14px' }} />
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Input card ── */}
      <motion.div
        animate={{
          borderColor: focused ? focusBorder : '#e2dff5',
          boxShadow: focused
            ? `0 0 0 3px ${focusRing}, 0 4px 18px rgba(0,0,0,0.06)`
            : '0 2px 10px rgba(0,0,0,0.04)',
        }}
        transition={{ duration: 0.18 }}
        style={{
          background: 'white',
          borderRadius: 18,
          border: '1.5px solid #e2dff5',
          overflow: 'hidden',
        }}
      >
        {/* Mode banners — one per active mode, stacked */}
        <AnimatePresence>
          {activeModeList.map(m => {
            const cfg = MODE_CONFIG[m]
            return (
              <motion.div
                key={m}
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 26, opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.17, ease: 'easeOut' }}
                style={{ overflow: 'hidden' }}
              >
                <div style={{
                  height: 26, display: 'flex', alignItems: 'center', gap: 7, padding: '0 14px',
                  background: cfg.bannerBg,
                  borderBottom: `1px solid ${cfg.bannerBorder}`,
                }}>
                  <span style={{ color: cfg.color, display: 'flex' }}>{cfg.icon}</span>
                  <span style={{ fontSize: 10.5, fontWeight: 600, color: cfg.color, letterSpacing: '0.01em', flex: 1 }}>
                    {cfg.tooltip}
                  </span>
                  <button
                    onClick={() => toggleMode(m)}
                    style={{
                      width: 14, height: 14, border: 'none', background: 'transparent',
                      cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: cfg.color, opacity: 0.5, padding: 0,
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.5' }}
                  >
                    <svg width="8" height="8" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <line x1="1" y1="1" x2="9" y2="9"/><line x1="9" y1="1" x2="1" y2="9"/>
                    </svg>
                  </button>
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={e => { setText(e.target.value); adjust() }}
          onKeyDown={handleKey}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={placeholder}
          rows={1}
          disabled={isLoading}
          style={{
            width: '100%', resize: 'none',
            padding: '14px 16px 4px',
            fontSize: 13.5, color: '#0f0a1e',
            fontFamily: 'Inter, sans-serif',
            lineHeight: 1.6, outline: 'none', border: 'none',
            background: 'transparent', minHeight: 52, maxHeight: 160,
          }}
          className="placeholder:text-[#c4c4cc]"
        />

        {/* Bottom toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '4px 10px 10px 12px', gap: 6,
        }}>

          {/* Left: attach button + active mode chips */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}>

            {/* ＋ Attach button */}
            <motion.button
              ref={attachBtnRef}
              onClick={() => setIsDropdownOpen(v => !v)}
              whileTap={{ scale: 0.94 }}
              animate={{
                background: isDropdownOpen ? 'rgba(124,58,237,0.08)' : 'transparent',
                borderColor: isDropdownOpen ? 'rgba(124,58,237,0.28)' : '#e5e7eb',
                color: isDropdownOpen ? '#7C3AED' : '#9ca3af',
              }}
              transition={{ duration: 0.14 }}
              style={{
                width: 28, height: 28, borderRadius: 8, border: '1px solid #e5e7eb',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', flexShrink: 0,
              }}
              onHoverStart={() => {
                if (attachBtnRef.current) {
                  attachBtnRef.current.style.background = isDropdownOpen ? 'rgba(124,58,237,0.08)' : '#f5f3ff'
                  attachBtnRef.current.style.color = '#7C3AED'
                  attachBtnRef.current.style.borderColor = 'rgba(124,58,237,0.22)'
                }
              }}
              onHoverEnd={() => {
                if (attachBtnRef.current && !isDropdownOpen) {
                  attachBtnRef.current.style.background = 'transparent'
                  attachBtnRef.current.style.color = '#9ca3af'
                  attachBtnRef.current.style.borderColor = '#e5e7eb'
                }
              }}
            >
              <motion.svg
                width="12" height="12" viewBox="0 0 12 12" fill="none"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                animate={{ rotate: isDropdownOpen ? 45 : 0 }}
                transition={{ duration: 0.18, ease: 'easeInOut' }}
              >
                <line x1="6" y1="1" x2="6" y2="11"/>
                <line x1="1" y1="6" x2="11" y2="6"/>
              </motion.svg>
            </motion.button>

            {/* Active mode chips — one per selected mode */}
            <AnimatePresence>
              {activeModeList.map(m => {
                const cfg = MODE_CONFIG[m]
                return (
                  <motion.div
                    key={m}
                    initial={{ opacity: 0, scale: 0.88, x: -6 }}
                    animate={{ opacity: 1, scale: 1, x: 0 }}
                    exit={{ opacity: 0, scale: 0.88, x: -4 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '3px 8px 3px 7px',
                      borderRadius: 99, height: 22, flexShrink: 0,
                      background: cfg.gradient,
                      boxShadow: cfg.shadow,
                    }}
                  >
                    <span style={{ color: 'white', display: 'flex', opacity: 0.9 }}>{cfg.icon}</span>
                    <span style={{ fontSize: 10.5, fontWeight: 600, color: 'white', letterSpacing: '0.01em', whiteSpace: 'nowrap' }}>
                      {cfg.label}
                    </span>
                    <button
                      onClick={() => toggleMode(m)}
                      style={{
                        width: 12, height: 12, border: 'none', background: 'transparent',
                        cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: 0, color: 'white', opacity: 0.6,
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
                      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.6' }}
                    >
                      <svg width="7" height="7" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                        <line x1="1" y1="1" x2="7" y2="7"/><line x1="7" y1="1" x2="1" y2="7"/>
                      </svg>
                    </button>
                  </motion.div>
                )
              })}
            </AnimatePresence>
          </div>

          {/* Right: char count + send */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <AnimatePresence>
              {text.length > 0 && (
                <motion.span
                  initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 6 }}
                  style={{ fontSize: 10.5, color: '#c4c4cc' }}
                >
                  {text.length}
                </motion.span>
              )}
            </AnimatePresence>
            {text.length === 0 && <span style={{ fontSize: 10.5, color: '#d1d5db' }}>↵ send</span>}

            {/* Send */}
            <motion.button
              onClick={handleSend}
              disabled={!canSend}
              whileHover={canSend ? { scale: 1.08 } : {}}
              whileTap={canSend ? { scale: 0.92 } : {}}
              animate={{
                background: canSend ? sendGrad : '#f0f0f5',
                boxShadow: canSend ? sendShadow : 'none',
              }}
              transition={{ duration: 0.2 }}
              style={{
                width: 32, height: 32, borderRadius: 10,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: 'none', cursor: canSend ? 'pointer' : 'not-allowed', flexShrink: 0,
              }}
            >
              {isLoading ? (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" className="animate-spin">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4"/>
                </svg>
              ) : (
                <motion.svg
                  width="13" height="13" viewBox="0 0 24 24" fill="none"
                  stroke={canSend ? 'white' : '#c0bdd6'}
                  strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                  animate={{ x: canSend ? [0, 1, 0] : 0 }}
                  transition={{ duration: 0.4, ease: 'easeOut' }}
                >
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </motion.svg>
              )}
            </motion.button>
          </div>
        </div>
      </motion.div>

      <p style={{ textAlign: 'center', fontSize: 10.5, color: '#c8c6d8', marginTop: 7 }}>
        CausalSense may produce errors. Verify important decisions independently.
      </p>

      <input
        ref={fileRef}
        type="file"
        accept=".csv,.xlsx,.xls,.json,.parquet,.sql,.txt,.tsv"
        style={{ display: 'none' }}
        onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = '' }}
      />
    </div>
  )
}
