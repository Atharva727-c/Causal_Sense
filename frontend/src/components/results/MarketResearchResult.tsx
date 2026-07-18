// Structured renderer for the market_research package output
// (data_profile + market_research report + optional causal DAG).
import DagView, { type Dag } from './DagView'

interface Source { title?: string; url?: string }
interface Finding { title?: string; detail?: string; sources?: Source[] }
interface Recommendation { recommendation?: string; rationale?: string; priority?: string }

export interface MarketResearchData {
  data_profile?: {
    domain?: string
    row_count?: number
    column_count?: number
    description?: string
    timeline?: { has_timeline?: boolean; start_date?: string; end_date?: string }
  }
  market_research?: {
    executive_summary?: string
    key_findings?: Finding[]
    opportunities?: string[]
    risks?: string[]
    recommendations?: Recommendation[]
    sources?: Source[]
  }
  dag?: Dag | null
  dag_unavailable_reason?: string | null
}

const PRIORITY_COLORS: Record<string, { bg: string; text: string }> = {
  high: { bg: '#fee2e2', text: '#b91c1c' },
  medium: { bg: '#fef3c7', text: '#b45309' },
  low: { bg: '#dcfce7', text: '#15803d' },
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 style={{ fontSize: 12.5, fontWeight: 700, color: '#4c1d95', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '18px 0 8px' }}>
      {children}
    </h4>
  )
}

export default function MarketResearchResult({ data }: { data: MarketResearchData }) {
  const profile = data.data_profile
  const mr = data.market_research

  return (
    <div style={{ fontSize: 13.5, lineHeight: 1.6, color: '#1f2937' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#0f0a1e' }}>Market Research</span>
        {profile?.domain && (
          <span style={{ fontSize: 11.5, fontWeight: 600, color: '#0d9488', background: 'rgba(13,148,136,0.08)', padding: '3px 9px', borderRadius: 99 }}>
            {profile.domain}
          </span>
        )}
        {profile?.row_count != null && (
          <span style={{ fontSize: 11.5, color: '#6b7280' }}>
            {profile.row_count.toLocaleString()} rows · {profile.column_count} columns
            {profile.timeline?.has_timeline && ` · ${profile.timeline.start_date} → ${profile.timeline.end_date}`}
          </span>
        )}
      </div>

      {mr?.executive_summary && (
        <p style={{ margin: 0, padding: '10px 14px', background: '#faf9ff', border: '1px solid #eceaf8', borderRadius: 10 }}>
          {mr.executive_summary}
        </p>
      )}

      {(mr?.key_findings?.length ?? 0) > 0 && (
        <>
          <SectionTitle>Key findings</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {mr!.key_findings!.map((f, i) => (
              <div key={i} style={{ padding: '10px 14px', border: '1px solid #eceaf8', borderRadius: 10 }}>
                <p style={{ margin: 0, fontWeight: 600, fontSize: 13 }}>{f.title}</p>
                <p style={{ margin: '4px 0 6px', color: '#4b5563', fontSize: 12.5 }}>{f.detail}</p>
                {(f.sources?.length ?? 0) > 0 && (
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {f.sources!.map((s, j) => (
                      <a key={j} href={s.url} target="_blank" rel="noreferrer"
                        style={{ fontSize: 11, color: '#7C3AED', background: 'rgba(124,58,237,0.06)', padding: '2px 8px', borderRadius: 99, textDecoration: 'none', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {s.title ?? s.url}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {(mr?.opportunities?.length ?? 0) > 0 && (
          <div>
            <SectionTitle>Opportunities</SectionTitle>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: '#374151' }}>
              {mr!.opportunities!.map((o, i) => <li key={i} style={{ marginBottom: 5 }}>{o}</li>)}
            </ul>
          </div>
        )}
        {(mr?.risks?.length ?? 0) > 0 && (
          <div>
            <SectionTitle>Risks</SectionTitle>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: '#374151' }}>
              {mr!.risks!.map((r, i) => <li key={i} style={{ marginBottom: 5 }}>{r}</li>)}
            </ul>
          </div>
        )}
      </div>

      {(mr?.recommendations?.length ?? 0) > 0 && (
        <>
          <SectionTitle>Recommendations</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {mr!.recommendations!.map((r, i) => {
              const pc = PRIORITY_COLORS[r.priority ?? ''] ?? { bg: '#f3f4f6', text: '#4b5563' }
              return (
                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 12px', border: '1px solid #eceaf8', borderRadius: 10 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', background: pc.bg, color: pc.text, padding: '2px 8px', borderRadius: 99, flexShrink: 0, marginTop: 2 }}>
                    {r.priority ?? '—'}
                  </span>
                  <div>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: 12.5 }}>{r.recommendation}</p>
                    <p style={{ margin: '2px 0 0', fontSize: 12, color: '#6b7280' }}>{r.rationale}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}

      {data.dag?.nodes?.length ? (
        <>
          <SectionTitle>Causal DAG</SectionTitle>
          <DagView dag={data.dag} />
        </>
      ) : data.dag_unavailable_reason ? (
        <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 14 }}>
          Causal DAG unavailable: {data.dag_unavailable_reason}
        </p>
      ) : null}
    </div>
  )
}
