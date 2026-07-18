import { Router, Request, Response } from 'express'
import { v4 as uuid } from 'uuid'
import multer from 'multer'
import path from 'path'
import fs from 'fs'
import { stmts } from '../db'

const router = Router()

const UPLOADS_DIR = path.join(__dirname, '..', 'data', 'uploads')
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true })

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOADS_DIR),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname)
    cb(null, `${uuid()}${ext}`)
  },
})

const ALLOWED_TYPES = new Set([
  'text/csv',
  'application/json',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/octet-stream',
  'text/plain',
  'application/x-parquet',
])

const upload = multer({
  storage,
  limits: { fileSize: 100 * 1024 * 1024 }, // 100 MB
  fileFilter: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase()
    const allowed = ['.csv', '.json', '.xlsx', '.xls', '.parquet', '.txt', '.tsv']
    if (allowed.includes(ext) || ALLOWED_TYPES.has(file.mimetype)) {
      cb(null, true)
    } else {
      cb(new Error(`Unsupported file type: ${ext}`))
    }
  },
})

function fileTypeFromName(name: string): string {
  const ext = path.extname(name).toLowerCase()
  const map: Record<string, string> = {
    '.csv': 'CSV', '.tsv': 'TSV', '.json': 'JSON',
    '.xlsx': 'XLSX', '.xls': 'XLS',
    '.parquet': 'Parquet', '.txt': 'TXT',
  }
  return map[ext] ?? ext.replace('.', '').toUpperCase()
}

function serializeFile(row: any) {
  return {
    id: row.id,
    name: row.name,
    originalName: row.original_name,
    size: row.size,
    fileType: row.file_type,
    mimeType: row.mime_type,
    createdAt: new Date(row.created_at).toISOString(),
  }
}

// GET /api/files
router.get('/', (_req: Request, res: Response) => {
  const files = (stmts.listFiles.all() as any[]).map(serializeFile)
  const { total } = stmts.totalFileSize.get() as any
  res.json({ files, totalSize: total })
})

// POST /api/files/upload
router.post('/upload', upload.single('file'), (req: Request, res: Response) => {
  if (!req.file) return res.status(400).json({ error: 'No file provided' })

  const id = uuid()
  const ts = Date.now()
  const fileType = fileTypeFromName(req.file.originalname)

  stmts.insertFile.run(
    id,
    req.file.filename,
    req.file.originalname,
    req.file.size,
    fileType,
    req.file.mimetype,
    req.file.path,
    ts,
  )

  const row = stmts.getFile.get(id) as any
  res.status(201).json(serializeFile(row))
})

// DELETE /api/files/:id
router.delete('/:id', (req: Request, res: Response) => {
  const file = stmts.getFile.get(req.params.id) as any
  if (!file) return res.status(404).json({ error: 'File not found' })

  // Remove from disk
  if (fs.existsSync(file.disk_path)) {
    fs.unlinkSync(file.disk_path)
  }

  stmts.deleteFile.run(req.params.id)
  res.json({ deleted: req.params.id })
})

// GET /api/files/:id/download
router.get('/:id/download', (req: Request, res: Response) => {
  const file = stmts.getFile.get(req.params.id) as any
  if (!file) return res.status(404).json({ error: 'File not found' })
  if (!fs.existsSync(file.disk_path)) return res.status(410).json({ error: 'File no longer on disk' })

  res.download(file.disk_path, file.original_name)
})

export default router
