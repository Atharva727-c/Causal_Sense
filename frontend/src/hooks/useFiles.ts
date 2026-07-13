import { useState, useCallback, useEffect } from 'react'
import type { UploadedFile } from '../types'

const API = '/api/files'

function getFileType(ext: string): UploadedFile['type'] {
  const e = ext.toLowerCase().replace('.', '')
  if (e === 'csv') return 'csv'
  if (e === 'xlsx' || e === 'xls') return 'excel'
  if (e === 'json') return 'json'
  if (e === 'parquet') return 'parquet'
  if (e === 'sql') return 'sql'
  return 'other'
}

function fromApiFile(raw: Record<string, unknown>): UploadedFile {
  const fileType = String(raw.fileType ?? '').toLowerCase()
  return {
    id: String(raw.id),
    name: String(raw.originalName ?? raw.name ?? ''),
    size: Number(raw.size ?? 0),
    type: getFileType(fileType),
    uploadedAt: new Date(String(raw.createdAt ?? Date.now())),
  }
}

export function useFiles() {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [isUploading, setIsUploading] = useState(false)

  // Load files from backend on mount
  useEffect(() => {
    fetch(API)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { files?: unknown[] } | null) => {
        if (data?.files) {
          setFiles((data.files as Record<string, unknown>[]).map(fromApiFile))
        }
      })
      .catch(() => {})
  }, [])

  const uploadFile = useCallback(async (file: File) => {
    setIsUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`${API}/upload`, { method: 'POST', body: formData })
      if (res.ok) {
        const raw = await res.json() as Record<string, unknown>
        const newFile = fromApiFile(raw)
        setFiles(prev => [newFile, ...prev])
        return newFile
      }
    } catch {
      /* fall through to local fallback */
    }

    // Local-only fallback (backend not available)
    const ext = file.name.split('.').pop() ?? ''
    const fallback: UploadedFile = {
      id: Math.random().toString(36).slice(2),
      name: file.name,
      size: file.size,
      type: getFileType(ext),
      uploadedAt: new Date(),
    }
    setFiles(prev => [fallback, ...prev])
    return fallback
  }, [])

  const removeFile = useCallback(async (id: string) => {
    setFiles(prev => prev.filter(f => f.id !== id))
    try {
      await fetch(`${API}/${id}`, { method: 'DELETE' })
    } catch {
      /* best-effort delete */
    }
  }, [])

  const totalUsed = files.reduce((sum, f) => sum + f.size, 0)
  const totalCapacity = 10 * 1024 * 1024 * 1024

  return { files, uploadFile, removeFile, isUploading, totalUsed, totalCapacity }
}
