export enum AppMode {
  SETUP = 'SETUP',
  USE = 'USE',
  LOGIN = 'LOGIN'
}

export enum FileType {
  PDF = 'pdf',
  CSV = 'csv',
  IMAGE = 'image',
  MODEL = 'model',
  FOLDER = 'folder'
}

export type ProjectStatus = 'setup' | 'processing' | 'ready';

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
  createdAt: string;
  updatedAt?: string;
}

export interface ProjectFile {
  id: string;
  name: string;
  type: FileType;
  children?: ProjectFile[];
  parentId?: string;
  storagePath?: string; // Supabase Storage path
  pageCount?: number;
  category?: string; // For Use Mode grouping (e.g., "A-101")
  file?: File; // The actual file object for rendering (local only)
}

export interface ContextPointer {
  id: string;
  pageId: string;
  title: string;
  description: string;
  textSpans?: string[];
  bboxX: number;
  bboxY: number;
  bboxWidth: number;
  bboxHeight: number;
  pngPath?: string;
  hasEmbedding?: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  timestamp: Date;
  referencedSheets?: {
    fileId: string;
    name: string;
    pointerCount: number;
  }[];
}

export interface Session {
  id: string;
  title: string;
  date: Date;
}
