// Renderer for the EDA pipeline result: markdown response with inline plot
// images (resolved from [[PLOT:cell]] markers) + follow-up chips.
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export interface EdaData {
  response?: string
  images?: Record<string, string[]> // cell number → data-URI PNGs
  followups?: string[]
  mock?: boolean
}

interface Props {
  data: EdaData
  onFollowup?: (question: string) => void
}

const PLOT_MARKER = /\[\[PLOT:(\d+)\]\]/g

function PlotImages({ cell, srcs }: { cell: string; srcs: string[] }) {
  return (
    <div style={{ margin: '10px 0' }}>
      {srcs.map((src, i) => (
        <img
          key={i}
          src={src}
          alt={`Plot from notebook cell ${cell}`}
          style={{
            display: 'block', maxWidth: '100%', borderRadius: 10,
            border: '1px solid #eceaf8', boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
            marginBottom: 6, background: 'white',
          }}
        />
      ))}
      <p style={{ margin: 0, fontSize: 10.5, color: '#9ca3af' }}>Notebook cell {cell}</p>
    </div>
  )
}

// Split the markdown on [[PLOT:n]] markers and interleave markdown segments
// with the corresponding plot images.
export function MarkdownWithPlots({ text, images }: { text: string; images?: Record<string, string[]> }) {
  const parts = (text ?? '').split(PLOT_MARKER)
  return (
    <div className="prose max-w-none">
      {parts.map((part, i) => {
        if (i % 2 === 1) {
          const srcs = images?.[part]
          return srcs?.length ? <PlotImages key={i} cell={part} srcs={srcs} /> : null
        }
        return part.trim() ? <ReactMarkdown key={i} remarkPlugins={[remarkGfm]}>{part}</ReactMarkdown> : null
      })}
    </div>
  )
}

export default function EdaResult({ data, onFollowup }: Props) {
  return (
    <div>
      {data.mock && (
        <p style={{ fontSize: 11, color: '#b45309', background: '#fef3c7', padding: '4px 10px', borderRadius: 8, display: 'inline-block', marginBottom: 8 }}>
          DIAL not configured — mock EDA output
        </p>
      )}
      <MarkdownWithPlots text={data.response ?? ''} images={data.images} />
      {(data.followups?.length ?? 0) > 0 && (
        <div style={{ marginTop: 12 }}>
          <p style={{ fontSize: 11.5, fontWeight: 600, color: '#6b7280', margin: '0 0 6px' }}>Suggested follow-ups</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {data.followups!.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowup?.(q)}
                style={{
                  fontSize: 12, color: '#4f46e5', background: 'rgba(79,70,229,0.06)',
                  border: '1px solid rgba(79,70,229,0.18)', borderRadius: 99,
                  padding: '5px 12px', cursor: 'pointer', textAlign: 'left',
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
