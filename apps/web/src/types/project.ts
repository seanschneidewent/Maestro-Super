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
  pageIndex?: number; // Zero-based index within multi-page PDF
  pointerCount?: number; // Number of context pointers on this page
  category?: string; // For Use Mode grouping (e.g., "A-101")
  file?: File; // The actual file object for rendering (local only)
}

// Hierarchy types for mind map visualization
export interface PointerSummary {
  id: string;
  title: string;
}

// Detail extracted from sheet-analyzer processing
export interface DetailSummary {
  id: string;
  title: string;
  number: string | null;
  shows: string | null;
  materials: string[];
  dimensions: string[];
  notes: string | null;
}

// Processing status for Brain Mode
export type PageProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface PageInHierarchy {
  id: string;
  pageName: string;
  pageIndex: number;  // Zero-based index within multi-page PDF
  processedPass1: boolean;
  processedPass2: boolean;
  pointerCount: number;
  pointers: PointerSummary[];
  // Brain Mode fields
  processingStatus?: PageProcessingStatus;
  details?: DetailSummary[];
}

export interface DisciplineInHierarchy {
  id: string;
  name: string;
  displayName: string;
  processed: boolean;
  pages: PageInHierarchy[];
}

export interface ProjectHierarchy {
  id: string;
  name: string;
  disciplines: DisciplineInHierarchy[];
}
