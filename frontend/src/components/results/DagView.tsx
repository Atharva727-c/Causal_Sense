// Renders the market-research causal DAG (nodes + edges) as a layered SVG.
// Responsive: drawn on a fixed coordinate system, scaled to the container via
// viewBox so boxes are never cut off; edge labels are staggered along their
// curve and drawn with a white halo so they stay legible without overlapping.

interface DagNode {
  id: string
  label: string
  type?: string
  description?: string
}

interface DagEdge {
  source: string
  target: string
  relationship?: string
  confidence?: string
  rationale?: string
}

export interface Dag {
  nodes: DagNode[]
  edges: DagEdge[]
}

const NODE_W = 176
const NODE_H = 58
const COL_GAP = 150
const ROW_GAP = 34
const PAD = 20

const TYPE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  external_factor: { fill: '#fff7ed', stroke: '#fdba74', text: '#9a3412' },
  dataset_variable: { fill: '#f5f3ff', stroke: '#c4b5fd', text: '#5b21b6' },
}

const REL_COLORS: Record<string, string> = {
  increases: '#059669',
  decreases: '#dc2626',
}

// Wrap a label into at most two centered lines without cutting words.
function wrapLabel(label: string, maxChars = 22): string[] {
  if (label.length <= maxChars) return [label]
  const words = label.split(' ')
  let line1 = ''
  let line2 = ''
  for (const w of words) {
    if (!line2 && (line1 + ' ' + w).trim().length <= maxChars) {
      line1 = (line1 + ' ' + w).trim()
    } else {
      line2 = (line2 + ' ' + w).trim()
    }
  }
  if (line2.length > maxChars) line2 = line2.slice(0, maxChars - 1) + '…'
  return [line1, line2]
}

// Point on the cubic bezier used for edges, at parameter t.
function bezierPoint(
  x1: number, y1: number, mx: number, x2: number, y2: number, t: number
): { x: number; y: number } {
  const u = 1 - t
  const x = u * u * u * x1 + 3 * u * u * t * mx + 3 * u * t * t * mx + t * t * t * x2
  const y = u * u * u * y1 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y2
  return { x, y }
}

function layout(dag: Dag) {
  // Longest-path layering: depth = 1 + max(depth of parents)
  const depth = new Map<string, number>()
  const incoming = new Map<string, string[]>()
  dag.nodes.forEach(n => incoming.set(n.id, []))
  dag.edges.forEach(e => {
    if (incoming.has(e.target)) incoming.get(e.target)!.push(e.source)
  })
  const resolve = (id: string, seen: Set<string>): number => {
    if (depth.has(id)) return depth.get(id)!
    if (seen.has(id)) return 0 // cycle guard
    seen.add(id)
    const parents = incoming.get(id) ?? []
    const d = parents.length === 0 ? 0 : 1 + Math.max(...parents.map(p => resolve(p, seen)))
    depth.set(id, d)
    return d
  }
  dag.nodes.forEach(n => resolve(n.id, new Set()))

  const columns = new Map<number, DagNode[]>()
  dag.nodes.forEach(n => {
    const d = depth.get(n.id) ?? 0
    if (!columns.has(d)) columns.set(d, [])
    columns.get(d)!.push(n)
  })

  const pos = new Map<string, { x: number; y: number }>()
  const maxRows = Math.max(...[...columns.values()].map(c => c.length))
  const height = PAD * 2 + maxRows * NODE_H + (maxRows - 1) * ROW_GAP
  columns.forEach((nodes, d) => {
    const colH = nodes.length * NODE_H + (nodes.length - 1) * ROW_GAP
    const y0 = (height - colH) / 2
    nodes.forEach((n, i) => {
      pos.set(n.id, {
        x: PAD + d * (NODE_W + COL_GAP),
        y: y0 + i * (NODE_H + ROW_GAP),
      })
    })
  })
  const width = PAD * 2 + columns.size * NODE_W + (columns.size - 1) * COL_GAP
  return { pos, width, height }
}

export default function DagView({ dag }: { dag: Dag }) {
  if (!dag?.nodes?.length) return null
  const { pos, width, height } = layout(dag)

  return (
    <div style={{ border: '1px solid #eceaf8', borderRadius: 12, background: '#fdfdff', padding: 4, overflowX: 'auto' }}>
      {/* Scales down to the container, but never below a readable size —
          narrower containers get a horizontal scrollbar instead of tiny text. */}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: 'auto', display: 'block', minWidth: Math.min(width, 660) }}
      >
        <defs>
          {['#059669', '#dc2626', '#6b7280'].map(c => (
            <marker
              key={c}
              id={`arrow-${c.slice(1)}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6.5"
              markerHeight="6.5"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
            </marker>
          ))}
        </defs>

        {/* Edges first (under the nodes) */}
        {dag.edges.map((e, i) => {
          const s = pos.get(e.source)
          const t = pos.get(e.target)
          if (!s || !t) return null
          const x1 = s.x + NODE_W
          const y1 = s.y + NODE_H / 2
          const x2 = t.x
          const y2 = t.y + NODE_H / 2
          const mx = (x1 + x2) / 2
          const color = REL_COLORS[e.relationship ?? ''] ?? '#6b7280'
          return (
            <g key={`e-${i}`}>
              <path
                d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2 - 3} ${y2}`}
                fill="none"
                stroke={color}
                strokeWidth={1.4}
                strokeOpacity={0.6}
                markerEnd={`url(#arrow-${color.slice(1)})`}
              >
                <title>{e.rationale ?? `${e.source} ${e.relationship ?? '→'} ${e.target}`}</title>
              </path>
            </g>
          )
        })}

        {/* Edge labels: staggered along each curve, with a white halo. A label
            is nudged to another spot on its curve if it would land on a node
            box, and dropped entirely (tooltip remains) if every spot collides. */}
        {(() => {
          const nodeRects = dag.nodes
            .map(n => pos.get(n.id))
            .filter((p): p is { x: number; y: number } => !!p)
            .map(p => ({ x: p.x, y: p.y, w: NODE_W, h: NODE_H }))
          const placed: { x: number; y: number; w: number; h: number }[] = []
          const collides = (x: number, y: number, w: number, h: number) =>
            [...nodeRects, ...placed].some(
              r => x < r.x + r.w && x + w > r.x && y < r.y + r.h && y + h > r.y
            )

          return dag.edges.map((e, i) => {
            if (!e.relationship) return null
            const s = pos.get(e.source)
            const t = pos.get(e.target)
            if (!s || !t) return null
            const x1 = s.x + NODE_W
            const y1 = s.y + NODE_H / 2
            const x2 = t.x
            const y2 = t.y + NODE_H / 2
            const mx = (x1 + x2) / 2
            const label = e.relationship.length > 24 ? e.relationship.slice(0, 22) + '…' : e.relationship
            const lw = label.length * 5.4
            const lh = 11
            const candidates = [[0.32, 0.5, 0.68][i % 3], 0.5, 0.32, 0.68, 0.42, 0.58]
            let spot: { x: number; y: number } | null = null
            for (const tc of candidates) {
              const p = bezierPoint(x1, y1, mx, x2, y2, tc)
              if (!collides(p.x - lw / 2, p.y - 4 - lh, lw, lh)) {
                spot = p
                break
              }
            }
            if (!spot) return null
            placed.push({ x: spot.x - lw / 2, y: spot.y - 4 - lh, w: lw, h: lh })
            const color = REL_COLORS[e.relationship] ?? '#6b7280'
            return (
              <text
                key={`l-${i}`}
                x={spot.x}
                y={spot.y - 4}
                textAnchor="middle"
                fontSize={9.5}
                fontWeight={600}
                fill={color}
                stroke="#fdfdff"
                strokeWidth={3}
                paintOrder="stroke"
              >
                {label}
              </text>
            )
          })
        })()}

        {/* Nodes */}
        {dag.nodes.map(n => {
          const p = pos.get(n.id)
          if (!p) return null
          const c = TYPE_COLORS[n.type ?? ''] ?? TYPE_COLORS.dataset_variable
          const lines = wrapLabel(n.label)
          const isExternal = n.type === 'external_factor'
          // Vertically center: label block + optional "external factor" tag
          const blockLines = lines.length + (isExternal ? 1 : 0)
          const lineH = 13
          const firstY = p.y + NODE_H / 2 - ((blockLines - 1) * lineH) / 2 + 4
          return (
            <g key={n.id}>
              <title>{n.description ?? n.label}</title>
              <rect x={p.x} y={p.y} width={NODE_W} height={NODE_H} rx={10} fill={c.fill} stroke={c.stroke} strokeWidth={1.2} />
              <text textAnchor="middle" fontSize={11.5} fontWeight={600} fill={c.text}>
                {lines.map((line, li) => (
                  <tspan key={li} x={p.x + NODE_W / 2} y={firstY + li * lineH}>
                    {line}
                  </tspan>
                ))}
              </text>
              {isExternal && (
                <text
                  x={p.x + NODE_W / 2}
                  y={firstY + lines.length * lineH}
                  textAnchor="middle"
                  fontSize={8.5}
                  fill={c.text}
                  fillOpacity={0.7}
                >
                  external factor
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
