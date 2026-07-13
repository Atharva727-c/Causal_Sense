import Database from 'better-sqlite3'
import path from 'path'
import fs from 'fs'

const DATA_DIR = path.join(__dirname, 'data')
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true })

export const db = new Database(path.join(DATA_DIR, 'causalsense.db'))

// Performance pragmas
db.pragma('journal_mode = WAL')
db.pragma('foreign_keys = ON')
db.pragma('synchronous = NORMAL')

// ── Schema ─────────────────────────────────────────────────────────────────

db.exec(`
  CREATE TABLE IF NOT EXISTS chats (
    id          TEXT    PRIMARY KEY,
    title       TEXT    NOT NULL DEFAULT 'New Chat',
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
  );

  CREATE TABLE IF NOT EXISTS messages (
    id          TEXT    PRIMARY KEY,
    chat_id     TEXT    NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role        TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
    content     TEXT    NOT NULL,
    created_at  INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
  CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
  CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);

  CREATE TABLE IF NOT EXISTS files (
    id            TEXT    PRIMARY KEY,
    name          TEXT    NOT NULL,
    original_name TEXT    NOT NULL,
    size          INTEGER NOT NULL,
    file_type     TEXT    NOT NULL,
    mime_type     TEXT    NOT NULL DEFAULT 'application/octet-stream',
    disk_path     TEXT    NOT NULL,
    created_at    INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at DESC);
`)

// ── Prepared statements ────────────────────────────────────────────────────

export const stmts = {
  // Chats
  listChats: db.prepare(`
    SELECT c.id, c.title, c.created_at, c.updated_at,
           (SELECT content FROM messages WHERE chat_id = c.id ORDER BY created_at DESC LIMIT 1) AS last_message
    FROM chats c
    ORDER BY c.updated_at DESC
  `),
  getChat: db.prepare('SELECT * FROM chats WHERE id = ?'),
  insertChat: db.prepare('INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)'),
  updateChatTitle: db.prepare('UPDATE chats SET title = ?, updated_at = ? WHERE id = ?'),
  touchChat: db.prepare('UPDATE chats SET updated_at = ? WHERE id = ?'),
  deleteChat: db.prepare('DELETE FROM chats WHERE id = ?'),

  // Messages
  getMessages: db.prepare('SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC'),
  getRecentMessages: db.prepare('SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?'),
  insertMessage: db.prepare('INSERT INTO messages (id, chat_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)'),
  countMessages: db.prepare('SELECT COUNT(*) AS n FROM messages WHERE chat_id = ?'),

  // Files
  listFiles: db.prepare('SELECT * FROM files ORDER BY created_at DESC'),
  getFile: db.prepare('SELECT * FROM files WHERE id = ?'),
  insertFile: db.prepare('INSERT INTO files (id, name, original_name, size, file_type, mime_type, disk_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'),
  deleteFile: db.prepare('DELETE FROM files WHERE id = ?'),
  totalFileSize: db.prepare('SELECT COALESCE(SUM(size), 0) AS total FROM files'),
}

console.log('✓ SQLite database ready')
