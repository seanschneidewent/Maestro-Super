export enum AppMode {
  SETUP = 'SETUP',
  USE = 'USE',
  LOGIN = 'LOGIN'
}

export enum FileType {
  PDF = 'PDF',
  CSV = 'CSV',
  IMAGE = 'IMAGE',
  MODEL = 'MODEL',
  FOLDER = 'FOLDER'
}

export interface ProjectFile {
  id: string;
  name: string;
  type: FileType;
  children?: ProjectFile[];
  parentId?: string;
  category?: string; // For Use Mode grouping (e.g., "A-101")
  file?: File; // The actual file object for rendering
}

export interface ContextPointer {
  id: string;
  fileId: string;
  pageNumber: number;
  bounds: {
    xNorm: number;
    yNorm: number;
    wNorm: number;
    hNorm: number;
  };
  title: string;
  description: string;
  status: 'generating' | 'complete' | 'error';
  snapshotUrl?: string; // Data URL
  aiAnalysis?: {
    technicalDescription?: string;
    tradeCategory?: string;
  };
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
