// Renderer for the Insight Builder pipeline report.

interface Insight {
  narrative?: string
  n?: number
  confidence_tier?: string
  [k: string]: unknown
}

export interface InsightsData {
  executive_summary?: string | null
  domain?: string | null
  n_rows?: number
  n_candidates_generated?: number
  n_candidates_after_triage?: number
  n_executed?: number
  n_validated?: number
  insights?: Insight[]
  top_insights?: Insight[]
  top_kpis?: Insight[]
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ padding: '8px 12px', background: '#faf9ff', border: '1px solid #eceaf8', borderRadius: 10, minWidth: 90 }}>
      <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#4c1d95' }}>{value ?? '—'}</p>
      <p style={{ margin: 0, fontSize: 10.5, color: '#6b7280' }}>{label}</p>
    </div>
  )
}

// The narrative string is "[Tag] headline sentence. (outlier trim clause.)" --
// pull the tag (for the badge) and the outlier clause (for a muted footer)
// out of the prose so the card headline reads as one clean sentence instead
// of a wall of bracketed/parenthetical noise.
const TAG_RE = /^\[([^\]]+)\]\s*/
const OUTLIER_RE = /\s*\(([^)]*outlier rows removed via[^)]*)\)\.?\s*$/

function parseNarrative(raw: string): { tag: string | null; headline: string; outlierNote: string | null } {
  const tagMatch = raw.match(TAG_RE)
  const tag = tagMatch?.[1] ?? null
  const rest = tagMatch ? raw.slice(tagMatch[0].length) : raw

  const outlierMatch = rest.match(OUTLIER_RE)
  if (!outlierMatch) return { tag, headline: rest.trim(), outlierNote: null }

  const headline = rest.slice(0, outlierMatch.index).trim()
  const outlierNote = outlierMatch[1].replace(/outlier rows removed via 2\.5\/97\.5 percentile trim\.?/i, 'trimmed (2.5/97.5 percentile)')
  return { tag, headline, outlierNote }
}

const BADGE_STYLE: Record<string, { bg: string; fg: string }> = {
  VALIDATED: { bg: 'rgba(16,185,129,0.1)', fg: '#047857' },
  'BUSINESS FACT': { bg: 'rgba(99,102,241,0.1)', fg: '#4338ca' },
  'NOT SIGNIFICANT': { bg: 'rgba(107,114,128,0.1)', fg: '#4b5563' },
  'TEST FAILED': { bg: 'rgba(239,68,68,0.1)', fg: '#b91c1c' },
}

function InsightCard({ insight }: { insight: Insight }) {
  const raw = insight.narrative
  if (!raw) return null
  const { tag, headline, outlierNote } = parseNarrative(raw)
  const badge = tag ? BADGE_STYLE[tag.toUpperCase()] ?? { bg: 'rgba(107,114,128,0.1)', fg: '#4b5563' } : null

  return (
    <div style={{
      padding: '9px 12px',
      background: '#fff',
      border: '1px solid #eceaf8',
      borderRadius: 10,
      marginBottom: 6,
    }}>
      {tag && (
        <span style={{
          display: 'inline-block',
          fontSize: 9.5,
          fontWeight: 700,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          padding: '2px 7px',
          borderRadius: 99,
          marginBottom: 5,
          background: badge!.bg,
          color: badge!.fg,
        }}>
          {tag}
        </span>
      )}
      <p style={{ margin: 0, fontSize: 12.5, color: '#1f2937', lineHeight: 1.5 }}>{headline}</p>
      {(insight.n != null || outlierNote) && (
        <p style={{ margin: '4px 0 0', fontSize: 10.5, color: '#9ca3af' }}>
          {insight.n != null && <>n={Number(insight.n).toLocaleString()}</>}
          {insight.n != null && outlierNote && ' · '}
          {outlierNote}
        </p>
      )}
    </div>
  )
}

export default function InsightsResult({ data }: { data: InsightsData }) {
  return (
    <div style={{ fontSize: 13.5, lineHeight: 1.6, color: '#1f2937' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#0f0a1e' }}>Insight Builder</span>
        {data.domain && (
          <span style={{ fontSize: 11.5, fontWeight: 600, color: '#db2777', background: 'rgba(236,72,153,0.08)', padding: '3px 9px', borderRadius: 99 }}>
            {data.domain}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <Stat label="rows" value={data.n_rows?.toLocaleString()} />
        <Stat label="hypotheses" value={data.n_candidates_generated} />
        <Stat label="after triage" value={data.n_candidates_after_triage} />
        <Stat label="executed" value={data.n_executed} />
        <Stat label="validated" value={data.n_validated} />
      </div>

      {data.executive_summary && (
        <p style={{ margin: '0 0 12px', padding: '10px 14px', background: '#faf9ff', border: '1px solid #eceaf8', borderRadius: 10 }}>
          {data.executive_summary}
        </p>
      )}

      {(() => {
        const topInsights = data.top_insights ?? data.insights?.slice(0, 10)
        const totalInsights = data.insights?.length ?? topInsights?.length ?? 0
        if (!topInsights || topInsights.length === 0) return null
        return (
          <>
            <p style={{ fontSize: 12.5, fontWeight: 700, color: '#4c1d95', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '0 0 8px' }}>
              Validated insights (top {topInsights.length}{totalInsights > topInsights.length ? ` of ${totalInsights}` : ''})
            </p>
            {topInsights.map((ins, i) => (
              <InsightCard key={i} insight={ins} />
            ))}
            {totalInsights > topInsights.length && (
              <p style={{ margin: '6px 0 0', fontSize: 11.5, color: '#6b7280' }}>
                Ask for more to see additional validated insights.
              </p>
            )}
          </>
        )
      })()}

      {(data.top_kpis?.length ?? 0) > 0 && (
        <>
          <p style={{ fontSize: 12.5, fontWeight: 700, color: '#4c1d95', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '14px 0 8px' }}>
            Top KPIs
          </p>
          {data.top_kpis!.map((k, i) => (
            <InsightCard key={i} insight={k} />
          ))}
        </>
      )}
    </div>
  )
}
