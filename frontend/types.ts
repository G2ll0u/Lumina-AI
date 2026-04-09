
export enum Role {
  USER = 'user',
  ASSISTANT = 'assistant',
  SYSTEM = 'system'
}

export interface SourceNode {
  url: string;
  snippet: string;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: Date;
  attachments?: string[];
  groundingUrls?: string[];
  sourceNodes?: SourceNode[];
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

export enum ModelType {
  PHI3 = 'phi3',
  MISTRAL_7B = 'mistral',
  LLAVA_7B = 'llava:7b',
  FLASH = 'gemini-1.5-flash'
}
