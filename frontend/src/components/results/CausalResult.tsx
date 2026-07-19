// Renderer for the full Causal Analysis report: LLM synthesis (summary, causal
// story, drivers, recommendations) + the causal DAG + EDA plot highlights +
// the validated-insight cards from the Insight Builder stage.
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import DagView, { type Dag } from './DagView'
import { type EdaData } from './EdaResult'
import InsightsResult, { type InsightsData } from './InsightsResult'
import type { MarketResearchData } from './MarketResearchResult'

interface KeyDriver {
  driver?: string
  effect?: string
  mechanism?: string
  evidence?: string
  confidence?: string
}

interface Recommendation {
  action?: string
  rationale?: string
  priority?: string
}

export interface CausalData {
  file?: string
  eda?: EdaData
  market_research?: MarketResearchData
  insights?: InsightsData
  synthesis?: {
    executive_summary?: string
    causal_story?: string
    key_drivers?: KeyDriver[]
    recommendations?: Recommendation[]
  }
}

const CONF_COLORS: Record<string, { bg: string; fg: string }> = {
  high: { bg: 'rgba(16,185,129,0.1)', fg: '#047857' },
  medium: { bg: 'rgba(245,158,11,0.12)', fg: '#b45309' },
  low: { bg: 'rgba(107,114,128,0.1)', fg: '#4b5563' },
}

const PRIORITY_COLORS: Record<string, { bg: string; fg: string }> = {
  high: { bg: '#fee2e2', fg: '#b91c1c' },
  medium: { bg: '#fef3c7', fg: '#b45309' },
  low: { bg: '#dcfce7', fg: '#15803d' },
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 style={{ fontSize: 12.5, fontWeight: 700, color: '#9a3412', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '20px 0 8px' }}>
      {children}
    </h4>
  )
}

export default function CausalResult({ data }: { data: CausalData }) {
  const syn = data.synthesis
  const dag = data.market_research?.dag as Dag | null | undefined
  const edaImages = data.eda?.images ?? {}
  const imageEntries = Object.entries(edaImages).slice(0, 4)

  return (
    <div style={{ fontSize: 13.5, lineHeight: 1.6, color: '#1f2937' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#0f0a1e' }}>Causal Analysis Report</span>
        {data.file && (
          <span style={{ fontSize: 11.5, fontWeight: 600, color: '#d97706', background: 'rgba(245,158,11,0.1)', padding: '3px 9px', borderRadius: 99 }}>
            {data.file}
          </span>
        )}
      </div>

      {syn?.executive_summary && (
        <p style={{ margin: 0, padding: '10px 14px', background: '#fffbf5', border: '1px solid #fde8cd', borderRadius: 10 }}>
          {syn.executive_summary}
        </p>
      )}

      {dag?.nodes?.length ? (
        <>
          <SectionTitle>Causal DAG</SectionTitle>
          <DagView dag={dag} />
        </>
      ) : null}

      {syn?.causal_story && (
        <>
          <SectionTitle>Causal story</SectionTitle>
          <div className="prose max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{syn.causal_story}</ReactMarkdown>
          </div>
        </>
      )}

      {(syn?.key_drivers?.length ?? 0) > 0 && (
        <>
          <SectionTitle>Key causal drivers</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {syn!.key_drivers!.map((d, i) => {
              const cc = CONF_COLORS[(d.confidence ?? '').toLowerCase()] ?? CONF_COLORS.low
              return (
                <div key={i} style={{ padding: '10px 14px', border: '1px solid #eceaf8', borderRadius: 10, background: 'white' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: 12.5 }}>{d.driver}</span>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>→ {d.effect}</span>
                    {d.confidence && (
                      <span style={{ fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', padding: '2px 7px', borderRadius: 99, background: cc.bg, color: cc.fg }}>
                        {d.confidence}
                      </span>
                    )}
                  </div>
                  {d.mechanism && <p style={{ margin: '4px 0 0', fontSize: 12, color: '#4b5563' }}>{d.mechanism}</p>}
                  {d.evidence && <p style={{ margin: '3px 0 0', fontSize: 10.5, color: '#9ca3af' }}>Evidence: {d.evidence}</p>}
                </div>
              )
            })}
          </div>
        </>
      )}

      {imageEntries.length > 0 && (
        <>
          <SectionTitle>EDA visual highlights</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 10 }}>
            {imageEntries.map(([cell, srcs]) =>
              srcs.slice(0, 1).map((src, i) => (
                <div key={`${cell}-${i}`}>
                  <img
                    src={src}
                    alt={`EDA plot from notebook cell ${cell}`}
                    style={{ width: '100%', borderRadius: 10, border: '1px solid #eceaf8', background: 'white' }}
                  />
                  <p style={{ margin: '2px 0 0', fontSize: 10.5, color: '#9ca3af' }}>Notebook cell {cell}</p>
                </div>
              ))
            )}
          </div>
        </>
      )}

      {data.insights && (
        <>
          <SectionTitle>Validated insights</SectionTitle>
          <InsightsResult data={data.insights} />
        </>
      )}

      {(syn?.recommendations?.length ?? 0) > 0 && (
        <>
          <SectionTitle>Recommendations</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {syn!.recommendations!.map((r, i) => {
              const pc = PRIORITY_COLORS[(r.priority ?? '').toLowerCase()] ?? { bg: '#f3f4f6', fg: '#4b5563' }
              return (
                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 12px', border: '1px solid #eceaf8', borderRadius: 10 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', background: pc.bg, color: pc.fg, padding: '2px 8px', borderRadius: 99, flexShrink: 0, marginTop: 2 }}>
                    {r.priority ?? '—'}
                  </span>
                  <div>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: 12.5 }}>{r.action}</p>
                    <p style={{ margin: '2px 0 0', fontSize: 12, color: '#6b7280' }}>{r.rationale}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
