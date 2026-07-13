import { Router, Request, Response } from 'express'
import multer from 'multer'
import path from 'path'
import fs from 'fs'

const router = Router()

const storage = multer.diskStorage({
  destination: (_, __, cb) => cb(null, path.join(__dirname, '../uploads')),
  filename: (_, file, cb) => {
    const unique = Date.now() + '-' + Math.round(Math.random() * 1e9)
    cb(null, unique + path.extname(file.originalname))
  },
})

const upload = multer({ storage, limits: { fileSize: 100 * 1024 * 1024 } })

router.post('/', upload.single('file'), (req: Request, res: Response) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' })

  const { originalname, size, mimetype, filename } = req.file
  return res.json({
    id: filename.split('.')[0],
    name: originalname,
    size,
    mimetype,
    uploadedAt: new Date().toISOString(),
    message: `File "${originalname}" uploaded successfully`,
  })
})

router.delete('/:filename', (req: Request, res: Response) => {
  const filePath = path.join(__dirname, '../uploads', String(req.params.filename))
  if (fs.existsSync(filePath)) fs.unlinkSync(filePath)
  return res.json({ success: true })
})

export default router
