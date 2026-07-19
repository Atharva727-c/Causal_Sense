import { motion } from 'framer-motion'
import type { FeatureId } from '../types'

interface Props {
  onFeature: (feature: FeatureId) => void
}

interface Action {
  gradient: string
  glow: string
  iconBg: string
  iconColor: string
  icon: React.ReactNode
  label: string
  desc: string
  feature: FeatureId
}

const ACTIONS: Action[] = [
  {
    gradient: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
    glow: 'rgba(79,70,229,0.2)',
    iconBg: 'rgba(79,70,229,0.08)',
    iconColor: '#4f46e5',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="13" width="5" height="8" rx="1"/>
        <rect x="9" y="8" width="5" height="13" rx="1"/>
        <rect x="16" y="3" width="5" height="18" rx="1"/>
        <line x1="4.5" y1="12" x2="11.5" y2="7" stroke="currentColor" strokeOpacity="0.5"/>
        <line x1="11.5" y1="7" x2="18.5" y2="2" stroke="currentColor" strokeOpacity="0.5"/>
      </svg>
    ),
    label: 'EDA',
    desc: 'Statistical deep-dive',
    feature: 'eda',
  },
  {
    gradient: 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)',
    glow: 'rgba(13,148,136,0.2)',
    iconBg: 'rgba(13,148,136,0.08)',
    iconColor: '#0d9488',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="2" y1="12" x2="22" y2="12"/>
        <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
      </svg>
    ),
    label: 'Market Research',
    desc: 'Competitive intelligence',
    feature: 'market_research',
  },
  {
    gradient: 'linear-gradient(135deg, #ec4899 0%, #f43f5e 100%)',
    glow: 'rgba(236,72,153,0.18)',
    iconBg: 'rgba(236,72,153,0.08)',
    iconColor: '#ec4899',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
      </svg>
    ),
    label: 'Insight Builder',
    desc: 'Validated data insights',
    feature: 'insight_builder',
  },
  {
    gradient: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)',
    glow: 'rgba(245,158,11,0.18)',
    iconBg: 'rgba(245,158,11,0.08)',
    iconColor: '#d97706',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="5" cy="6" r="2.2"/>
        <circle cx="19" cy="6" r="2.2"/>
        <circle cx="12" cy="18" r="2.2"/>
        <line x1="6.5" y1="7.5" x2="10.5" y2="16.2"/>
        <line x1="17.5" y1="7.5" x2="13.5" y2="16.2"/>
        <line x1="7.2" y1="6" x2="16.8" y2="6"/>
      </svg>
    ),
    label: 'Causal Analysis',
    desc: 'EDA → Research → Insights',
    feature: 'causal_analysis',
  },
]

export default function QuickActions({ onFeature }: Props) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 11,
        width: '100%',
        maxWidth: 720,
      }}
    >
      {ACTIONS.map((action, i) => (
        <motion.button
          key={i}
          onClick={() => onFeature(action.feature)}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06 + 0.04, type: 'spring', stiffness: 340, damping: 24 }}
          whileHover={{
            y: -3,
            boxShadow: `0 8px 28px ${action.glow}, 0 2px 8px rgba(0,0,0,0.05)`,
            borderColor: `${action.iconColor}38`,
          }}
          whileTap={{ scale: 0.98 }}
          style={{
            display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
            gap: 10, padding: '15px 14px 13px', borderRadius: 16, textAlign: 'left',
            background: 'white',
            border: '1px solid #eceaf8',
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
            cursor: 'pointer',
            position: 'relative', overflow: 'hidden',
          }}
        >
          {/* Gradient glow overlay on hover */}
          <motion.div
            initial={{ opacity: 0 }}
            whileHover={{ opacity: 1 }}
            style={{
              position: 'absolute', inset: 0, pointerEvents: 'none',
              background: `radial-gradient(circle at 30% 30%, ${action.iconBg}, transparent 70%)`,
            }}
          />

          {/* Icon */}
          <div
            style={{
              width: 36, height: 36, borderRadius: 10,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: action.iconBg, color: action.iconColor,
              flexShrink: 0, position: 'relative',
            }}
          >
            {action.icon}
          </div>

          {/* Text */}
          <div style={{ position: 'relative' }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: '#1f2937', marginBottom: 3, lineHeight: 1.3 }}>
              {action.label}
            </p>
            <p style={{ fontSize: 10.5, color: '#9ca3af', lineHeight: 1.4 }}>
              {action.desc}
            </p>
          </div>

          {/* Bottom accent bar */}
          <motion.div
            initial={{ scaleX: 0 }}
            whileHover={{ scaleX: 1 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            style={{
              position: 'absolute', bottom: 0, left: 0, right: 0,
              height: 2.5, borderRadius: '0 0 16px 16px',
              background: action.gradient,
              transformOrigin: 'left',
            }}
          />
        </motion.button>
      ))}
    </div>
  )
}
