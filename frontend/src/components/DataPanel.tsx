import { useRef, useState } from 'react'
import type { UploadedFile } from '../types'

interface Props {
  files: UploadedFile[]
  onUpload: (file: File) => void
  onRemove?: (id: string) => void
  isUploading: boolean
  totalUsed: number
  totalCapacity: number
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
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

const TYPE_CONFIG: Record<UploadedFile['type'], { color: string; bg: string; border: string; label: string }> = {
  csv:     { color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0', label: 'CSV' },
  excel:   { color: '#15803d', bg: '#f0fdf4', border: '#bbf7d0', label: 'XLS' },
  json:    { color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe', label: 'JSON' },
  parquet: { color: '#7C3AED', bg: '#f5f3ff', border: '#ddd6fe', label: 'PAR' },
  sql:     { color: '#d97706', bg: '#fffbeb', border: '#fde68a', label: 'SQL' },
  other:   { color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb', label: 'FILE' },
}

function FileIcon({ type }: { type: UploadedFile['type'] }) {
  const cfg = TYPE_CONFIG[type]
  return (
    <div
      style={{
        width: 36, height: 36, borderRadius: 10, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: cfg.bg, border: `1.5px solid ${cfg.border}`,
      }}
    >
      <span style={{ fontSize: 8.5, fontWeight: 700, letterSpacing: '0.06em', color: cfg.color }}>
        {cfg.label}
      </span>
    </div>
  )
}

export default function DataPanel({ files, onUpload, onRemove, isUploading, totalUsed, totalCapacity }: Props) {
  const [isDragging, setIsDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) onUpload(file)
  }

  const usedGB = (totalUsed / 1024 / 1024 / 1024).toFixed(1)
  const capGB = (totalCapacity / 1024 / 1024 / 1024).toFixed(0)
  const pct = Math.min((totalUsed / totalCapacity) * 100, 100)

  return (
    <aside
      style={{
        width: 276, minWidth: 276,
        background: '#f9f8ff',
        borderLeft: '1px solid #e8e2fe',
        display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden',
      }}
    >
      {/* ── Upload dropzone ── */}
      <div style={{ padding: '16px 16px 12px', flexShrink: 0 }}>
        <div
          onClick={() => fileRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          style={{
            border: `1.5px dashed ${isDragging ? '#7C3AED' : '#c4b5fd'}`,
            borderRadius: 16,
            background: isDragging ? 'rgba(124,58,237,0.04)' : 'white',
            padding: '20px 16px',
            cursor: 'pointer',
            transition: 'all 0.18s',
            boxShadow: isDragging ? '0 0 0 3px rgba(124,58,237,0.1)' : 'none',
          }}
          onMouseEnter={e => {
            const el = e.currentTarget as HTMLDivElement
            if (!isDragging) {
              el.style.borderColor = '#a78bfa'
              el.style.background = '#fdfaff'
            }
          }}
          onMouseLeave={e => {
            const el = e.currentTarget as HTMLDivElement
            if (!isDragging) {
              el.style.borderColor = '#c4b5fd'
              el.style.background = 'white'
            }
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, textAlign: 'center' }}>
            {/* Icon container */}
            <div
              style={{
                width: 48, height: 48, borderRadius: 14,
                background: 'linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)',
                boxShadow: '0 3px 12px rgba(124,58,237,0.1)',
                border: '1px solid rgba(124,58,237,0.1)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {isUploading ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="2" strokeLinecap="round" className="animate-spin">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4"/>
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="1.9" strokeLinecap="round">
                  <polyline points="16 16 12 12 8 16"/>
                  <line x1="12" y1="12" x2="12" y2="21"/>
                  <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/>
                </svg>
              )}
            </div>
            <div>
              <p style={{ fontSize: 12.5, fontWeight: 600, color: '#5B21B6', marginBottom: 3 }}>
                {isUploading ? 'Uploading…' : 'Drop files here'}
              </p>
              <p style={{ fontSize: 11.5, color: '#a78bfa', marginBottom: 0 }}>or click to browse</p>
            </div>
            <p style={{ fontSize: 10.5, color: '#c4b5fd', lineHeight: 1.5 }}>
              CSV · Excel · JSON · Parquet · SQL
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            style={{ display: 'none' }}
            accept=".csv,.xlsx,.xls,.json,.parquet,.sql"
            onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = '' }}
          />
        </div>
      </div>

      {/* ── Files header ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 18px 10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.01em', color: '#374151' }}>
            Uploaded Files
          </span>
          {files.length > 0 && (
            <span
              style={{
                fontSize: 10, fontWeight: 600, color: '#7C3AED',
                background: 'rgba(124,58,237,0.1)', borderRadius: 20,
                padding: '1px 7px',
              }}
            >
              {files.length}
            </span>
          )}
        </div>
        <button
          style={{
            width: 26, height: 26, borderRadius: 7, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            color: '#9ca3af', border: 'none', background: 'transparent',
            cursor: 'pointer', transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            const b = e.currentTarget
            b.style.background = '#ede9fe'
            b.style.color = '#7C3AED'
          }}
          onMouseLeave={e => {
            const b = e.currentTarget
            b.style.background = 'transparent'
            b.style.color = '#9ca3af'
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
          </svg>
        </button>
      </div>

      {/* ── File list ── */}
      <div className="light-scroll" style={{ flex: 1, overflowY: 'auto', padding: '0 10px' }}>
        {files.map(file => (
          <div
            key={file.id}
            className="group"
            style={{
              display: 'flex', alignItems: 'center', gap: 11,
              padding: '9px 10px', borderRadius: 11, marginBottom: 3,
              cursor: 'default', transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              const el = e.currentTarget as HTMLDivElement
              el.style.background = 'white'
              el.style.boxShadow = '0 2px 12px rgba(0,0,0,0.06)'
            }}
            onMouseLeave={e => {
              const el = e.currentTarget as HTMLDivElement
              el.style.background = 'transparent'
              el.style.boxShadow = 'none'
            }}
          >
            <FileIcon type={file.type} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{
                fontSize: 12, fontWeight: 600, color: '#111827',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                marginBottom: 2,
              }}>
                {file.name}
              </p>
              <p style={{ fontSize: 10.5, color: '#9ca3af' }}>
                {file.type.toUpperCase()} · {formatSize(file.size)} · {timeAgo(file.uploadedAt)}
              </p>
            </div>
            <button
              onClick={() => onRemove?.(file.id)}
              style={{
                width: 22, height: 22, borderRadius: 6,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#d1d5db', border: 'none', background: 'transparent',
                cursor: 'pointer', opacity: 0, transition: 'all 0.15s',
              }}
              className="group-hover:opacity-100"
              title="Remove file"
              onMouseEnter={e => {
                const b = e.currentTarget
                b.style.color = '#ef4444'
                b.style.background = '#fef2f2'
              }}
              onMouseLeave={e => {
                const b = e.currentTarget
                b.style.color = '#d1d5db'
                b.style.background = 'transparent'
              }}
            >
              <svg width="9" height="9" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="2" y1="2" x2="12" y2="12"/>
                <line x1="12" y1="2" x2="2" y2="12"/>
              </svg>
            </button>
          </div>
        ))}
        {files.length === 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '28px 0', gap: 8 }}>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.4" strokeLinecap="round">
              <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/>
              <polyline points="13 2 13 9 20 9"/>
            </svg>
            <p style={{ fontSize: 11.5, color: '#9ca3af' }}>No files uploaded yet</p>
          </div>
        )}
      </div>

      {/* ── Storage ── */}
      <div style={{ padding: '12px 18px 10px', borderTop: '1px solid #ede9fe' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 11.5, fontWeight: 600, color: '#374151' }}>Storage</span>
          <span style={{ fontSize: 11, fontWeight: 600, color: '#7C3AED' }}>{usedGB} / {capGB} GB</span>
        </div>
        <div style={{ height: 5, borderRadius: 99, background: '#ede9fe', overflow: 'hidden' }}>
          <div
            style={{
              width: `${pct}%`, height: '100%', borderRadius: 99,
              background: 'linear-gradient(90deg, #7C3AED 0%, #a78bfa 100%)',
              boxShadow: '0 0 6px rgba(124,58,237,0.3)',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
      </div>

      {/* ── View all datasets ── */}
      <button
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '11px 18px 13px', fontSize: 12.5, fontWeight: 600, color: '#7C3AED',
          border: 'none', background: 'transparent', cursor: 'pointer',
          borderTop: '1px solid #ede9fe', transition: 'background 0.15s', width: '100%',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#f5f0ff' }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
      >
        <span>View all datasets</span>
        <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <polyline points="7 15 13 10 7 5"/>
        </svg>
      </button>
    </aside>
  )
}
