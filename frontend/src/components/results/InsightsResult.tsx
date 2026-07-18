// Renderer for the Insight Builder pipeline report.

interface Insight {
  narrative?: string
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

      {(data.insights?.length ?? 0) > 0 && (
        <>
          <p style={{ fontSize: 12.5, fontWeight: 700, color: '#4c1d95', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '0 0 8px' }}>
            Validated insights
          </p>
          <ol style={{ margin: 0, paddingLeft: 20 }}>
            {data.insights!.map((ins, i) => (
              <li key={i} style={{ marginBottom: 8, fontSize: 12.5, color: '#374151' }}>
                {ins.narrative ?? JSON.stringify(ins)}
              </li>
            ))}
          </ol>
        </>
      )}

      {(data.top_kpis?.length ?? 0) > 0 && (
        <>
          <p style={{ fontSize: 12.5, fontWeight: 700, color: '#4c1d95', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '14px 0 8px' }}>
            Top KPIs
          </p>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {data.top_kpis!.map((k, i) => (
              <li key={i} style={{ marginBottom: 6, fontSize: 12.5, color: '#374151' }}>
                {(k.narrative as string) ?? JSON.stringify(k)}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
