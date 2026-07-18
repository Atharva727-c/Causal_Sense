export type AgentMode = 'eda' | 'market_research' | null
export type ActiveMode = NonNullable<AgentMode>

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  streaming?: boolean
}

export interface Chat {
  id: string
  title: string
  messages: Message[]
  createdAt: Date
}

export interface UploadedFile {
  id: string
  name: string
  size: number
  type: 'csv' | 'excel' | 'json' | 'parquet' | 'sql' | 'other'
  uploadedAt: Date
  context?: string
}
