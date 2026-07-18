// Renderer for the EDA pipeline result: markdown response + follow-up chips.
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export interface EdaData {
  response?: string
  followups?: string[]
  mock?: boolean
}

interface Props {
  data: EdaData
  onFollowup?: (question: string) => void
}

export default function EdaResult({ data, onFollowup }: Props) {
  return (
    <div>
      {data.mock && (
        <p style={{ fontSize: 11, color: '#b45309', background: '#fef3c7', padding: '4px 10px', borderRadius: 8, display: 'inline-block', marginBottom: 8 }}>
          DIAL not configured — mock EDA output
        </p>
      )}
      <div className="prose max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.response ?? ''}</ReactMarkdown>
      </div>
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
