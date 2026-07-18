export type AgentMode = 'eda' | 'market_research' | null
export type ActiveMode = NonNullable<AgentMode>

export type FeatureId = 'eda' | 'market_research' | 'insight_builder' | 'causal_analysis'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  streaming?: boolean
  // Structured feature results (rendered by dedicated components instead of markdown)
  kind?: 'text' | 'eda' | 'market_research' | 'insights'
  data?: unknown
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
