import { supabase } from './supabase';
import type { ProjectHierarchy } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

// Error types from backend
export type ApiErrorType = 'rate_limit' | 'validation' | 'not_found' | 'auth' | 'server_error';

export interface ApiErrorResponse {
  detail: string | Record<string, unknown>;
  error_type?: ApiErrorType;
  error_id?: string;
  errors?: Array<{ field: string; message: string }>;
  // Rate limit specific
  limits?: {
    requests?: { used: number; max: number };
    tokens?: { used: number; max: number };
    pointers?: { used: number; max: number };
  };
  retry_after?: number;
}

class ApiError extends Error {
  public errorType: ApiErrorType;
  public errorId?: string;
  public response?: ApiErrorResponse;

  constructor(
    public status: number,
    message: string,
    response?: ApiErrorResponse
  ) {
    super(message);
    this.name = 'ApiError';
    this.response = response;
    this.errorId = response?.error_id;

    // Determine error type from response or status
    if (response?.error_type) {
      this.errorType = response.error_type;
    } else if (status === 429) {
      this.errorType = 'rate_limit';
    } else if (status === 404) {
      this.errorType = 'not_found';
    } else if (status === 400 || status === 422) {
      this.errorType = 'validation';
    } else if (status === 401 || status === 403) {
      this.errorType = 'auth';
    } else {
      this.errorType = 'server_error';
    }
  }
}

// Helper functions for error type checking
export function isRateLimitError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.errorType === 'rate_limit';
}

export function isValidationError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.errorType === 'validation';
}

export function isNotFoundError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.errorType === 'not_found';
}

export function isAuthError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.errorType === 'auth';
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}

export function getRateLimitInfo(error: ApiError): {
  retryAfter: number;
  limits?: ApiErrorResponse['limits'];
} | null {
  if (!isRateLimitError(error)) return null;
  return {
    retryAfter: error.response?.retry_after || 3600,
    limits: error.response?.limits,
  };
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = options;

  // Get auth token if user is logged in
  const { data: { session } } = await supabase.auth.getSession();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!response.ok) {
    const errorResponse: ApiErrorResponse = await response.json().catch(() => ({
      detail: 'Unknown error',
    }));

    // Extract message from error response
    let message = 'Request failed';
    if (Array.isArray(errorResponse.detail)) {
      // FastAPI validation errors
      message = (errorResponse.detail as Array<{ loc?: string[]; msg?: string }>)
        .map((e) => `${e.loc?.join('.')}: ${e.msg}`)
        .join(', ');
    } else if (typeof errorResponse.detail === 'string') {
      message = errorResponse.detail;
    } else if (typeof errorResponse.detail === 'object' && errorResponse.detail !== null) {
      // Rate limit errors have detail as an object
      message = (errorResponse.detail as { detail?: string }).detail || 'Request failed';
    }

    // Format validation errors
    if (errorResponse.errors?.length) {
      message = errorResponse.errors.map((e) => `${e.field}: ${e.message}`).join(', ');
    }

    console.error('API Error:', response.status, errorResponse);
    throw new ApiError(response.status, message, errorResponse);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Types matching backend schemas
export interface Project {
  id: string;
  name: string;
  status: 'setup' | 'processing' | 'ready';
  createdAt: string;
  updatedAt?: string;
}

export interface ProjectFileFlat {
  id: string;
  projectId: string;
  name: string;
  fileType: 'pdf' | 'image' | 'csv' | 'model' | 'folder';
  storagePath?: string;
  pageCount?: number;
  isFolder: boolean;
  parentId?: string;
  createdAt: string;
}

export interface ProjectFileTree {
  id: string;
  name: string;
  type: 'pdf' | 'image' | 'csv' | 'model' | 'folder';
  parentId?: string;
  children?: ProjectFileTree[];
  category?: string;
}

export interface Bounds {
  xNorm: number;
  yNorm: number;
  wNorm: number;
  hNorm: number;
}

export interface ContextPointerResponse {
  id: string;
  fileId: string;
  pageNumber: number;
  bounds: Bounds;
  title?: string;
  description?: string;
  status: 'generating' | 'complete' | 'error';
  snapshotUrl?: string;
  aiAnalysis?: {
    technicalDescription?: string;
    tradeCategory?: string;
    elements?: Array<Record<string, unknown>>;
    measurements?: Array<Record<string, unknown>>;
  };
  committedAt?: string;
  createdAt: string;
}

// Upload types
export interface PageUploadData {
  pageName: string;
  fileName: string;
  storagePath: string;
}

export interface DisciplineUploadData {
  code: string;
  displayName: string;
  pages: PageUploadData[];
}

export interface BulkUploadRequest {
  projectName: string;
  disciplines: DisciplineUploadData[];
}

export interface PageInDisciplineResponse {
  id: string;
  pageName: string;
  filePath: string;
  pageIndex: number;  // Zero-based index within multi-page PDF
  processedPass1: boolean;
  processedPass2: boolean;
}

export interface DisciplineWithPagesResponse {
  id: string;
  projectId: string;
  name: string;
  displayName: string;
  processed: boolean;
  pages: PageInDisciplineResponse[];
}

export interface ProjectInUploadResponse {
  id: string;
  name: string;
  createdAt: string;
  updatedAt?: string;
}

export interface BulkUploadResponse {
  project: ProjectInUploadResponse;
  disciplines: DisciplineWithPagesResponse[];
}

// Discipline types (matching backend schema)
export interface DisciplineResponse {
  id: string;
  projectId: string;
  name: string;
  displayName: string;
  summary?: string;
  processed: boolean;
  createdAt: string;
  updatedAt?: string;
}

// Semantic word from sheet-analyzer
export interface SemanticWord {
  id: number;
  text: string;
  confidence: number;
  bbox: {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
    width: number;
    height: number;
  };
  region_type?: string;  // detail, notes, schedule, title_block, legend, plan_area
  role?: string;  // detail_title, dimension, material_spec, note_text, sheet_number, etc.
}

// Semantic index from sheet-analyzer
export interface SemanticIndex {
  words: SemanticWord[];
  tile_bounds?: Array<{ x: number; y: number; width: number; height: number }>;
  quadrant_classifications?: Record<string, unknown>;
}

// Detail extracted from context markdown
export interface PageDetail {
  id?: string;
  title: string;
  number: string | null;
  shows: string | null;
  materials: string[];
  dimensions: string[];
  notes: string | null;
}

// Page types (matching backend schema)
export interface PageResponse {
  id: string;
  disciplineId: string;
  pageName: string;
  filePath: string;
  pageIndex: number;  // Zero-based index within multi-page PDF
  initialContext?: string;
  fullContext?: string;
  processedPass1: boolean;
  processedPass2: boolean;
  // PNG pipeline fields
  pageImagePath?: string;
  pageImageReady: boolean;
  fullPageText?: string;
  ocrData?: OcrSpan[];
  processedOcr: boolean;

  // Agentic Vision fields
  regions?: Region[];
  sheetReflection?: string;
  pageType?: string;
  crossReferences?: string[];
  sheetInfo?: SheetInfo;
  masterIndex?: MasterIndex;
  questionsAnswered?: string[];
  processingTimeMs?: number;
  processingError?: string;

  // Legacy (kept for backwards compat)
  semanticIndex?: SemanticIndex;
  contextMarkdown?: string;
  details?: PageDetail[];
  processingStatus?: 'pending' | 'processing' | 'completed' | 'failed';
  processedAt?: string;
  createdAt: string;
  updatedAt?: string;
}

export interface SheetInfo {
  number: string;
  title: string;
  fullTitle: string;
  scale?: string;
  date?: string;
  discipline?: string;
}

export interface MasterIndex {
  keywords?: string[];
  areasShown?: Array<{ name: string; notes?: string }>;
  items?: Array<{
    name: string;
    action?: string;
    location?: string;
    keynote?: string;
    details?: string;
  }>;
  keynotes?: Array<{ number: string; text: string }>;
  dimensions?: string[];
  specifications?: string[];
  crossReferences?: Array<{ sheet: string; context?: string }>;
}

export interface Region {
  id: string;
  type: 'detail' | 'legend' | 'notes' | 'title_block' | 'schedule' | 'plan' | 'general';
  detailNumber?: string;
  label: string;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  confidence?: number;
  scale?: string;
  shows?: string;
  regionIndex?: {
    areas?: string[];
    items?: Array<{ name: string; action?: string }>;
    materials?: string[];
    keynotesShown?: string[];
    dimensions?: string[];
    crossRefs?: string[];
  };
}

// Pointer types (matching backend schema)
export interface OcrSpan {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
}

export interface PointerReferenceResponse {
  id: string;
  targetPageId: string;
  targetPageName: string;
  justification: string;
}

export interface PointerResponse {
  id: string;
  pageId: string;
  title: string;
  description: string;
  textSpans?: string[];
  ocrData?: OcrSpan[];  // Word-level OCR with positions for highlighting
  bboxX: number;
  bboxY: number;
  bboxWidth: number;
  bboxHeight: number;
  pngPath?: string;
  hasEmbedding: boolean;
  references?: PointerReferenceResponse[];
  createdAt: string;
  updatedAt?: string;
}

// Query types (matching backend schema)
export interface QueryTraceStep {
  type: 'reasoning' | 'tool_call' | 'tool_result' | 'response' | 'thinking';
  content?: string;
  tool?: string;
  input?: Record<string, unknown>;
  result?: Record<string, unknown>;
}

export interface QueryPageResponse {
  id: string;
  pageId: string;
  pageOrder: number;
  pointersShown?: Array<{ pointerId: string }>;
  // Page details
  pageName?: string;
  filePath?: string;
  disciplineId?: string;
}

export interface QueryResponse {
  id: string;
  userId: string;
  projectId?: string;
  conversationId?: string;
  queryText: string;
  responseText?: string;
  displayTitle?: string;
  sequenceOrder?: number;
  referencedPointers?: Array<{ pointerId: string }>;
  trace?: QueryTraceStep[];
  tokensUsed?: number;
  pages?: QueryPageResponse[];
  createdAt: string;
}

// Conversation types (matching backend schema)
export interface ConversationResponse {
  id: string;
  userId: string;
  projectId: string;
  createdAt: string;
  updatedAt: string;
  title?: string | null;
}

export interface ConversationWithQueriesResponse extends ConversationResponse {
  queries: QueryResponse[];
}

// Processing types
export interface PageProcessResult {
  pageId: string;
  success: boolean;
  ocrSuccess: boolean;
  pngSuccess: boolean;
  aiSuccess: boolean;
  error?: string;
}

export interface ProcessUploadsResult {
  total: number;
  ocrCompleted: number;
  pngCompleted: number;
  aiCompleted: number;
  failed: number;
  results: PageProcessResult[];
}

// API functions

// Projects
export const api = {
  projects: {
    list: () => request<Project[]>('/projects'),
    create: (name: string) => request<Project>('/projects', {
      method: 'POST',
      body: { name },
    }),
    get: (id: string) => request<Project>(`/projects/${id}`),
    getFull: (id: string) => request<BulkUploadResponse>(`/projects/${id}/full`),
    getHierarchy: (id: string) => request<ProjectHierarchy>(`/projects/${id}/hierarchy`),
    update: (id: string, data: { name?: string; status?: string }) =>
      request<Project>(`/projects/${id}`, { method: 'PATCH', body: data }),
    delete: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  },

  upload: {
    bulkCreate: (data: BulkUploadRequest) =>
      request<BulkUploadResponse>('/projects/upload', {
        method: 'POST',
        body: data,
      }),
  },

  disciplines: {
    list: (projectId: string) =>
      request<DisciplineResponse[]>(`/projects/${projectId}/disciplines`),
    create: (projectId: string, data: { name: string; displayName: string }) =>
      request<DisciplineResponse>(`/projects/${projectId}/disciplines`, {
        method: 'POST',
        body: data,
      }),
    get: (id: string) => request<DisciplineResponse>(`/disciplines/${id}`),
    update: (id: string, data: { name?: string; displayName?: string; summary?: string; processed?: boolean }) =>
      request<DisciplineResponse>(`/disciplines/${id}`, { method: 'PATCH', body: data }),
    delete: (id: string) => request<void>(`/disciplines/${id}`, { method: 'DELETE' }),
  },

  pages: {
    list: (disciplineId: string) =>
      request<PageResponse[]>(`/disciplines/${disciplineId}/pages`),
    create: (disciplineId: string, data: { pageName: string; filePath: string }) =>
      request<PageResponse>(`/disciplines/${disciplineId}/pages`, {
        method: 'POST',
        body: data,
      }),
    get: (id: string) => request<PageResponse>(`/pages/${id}`),
    update: (id: string, data: { pageName?: string; filePath?: string; initialContext?: string; fullContext?: string; regions?: Region[] }) =>
      request<PageResponse>(`/pages/${id}`, { method: 'PATCH', body: data }),
    delete: (id: string) => request<void>(`/pages/${id}`, { method: 'DELETE' }),
    retryPng: (id: string) =>
      request<{ success: boolean; pageImagePath?: string; error?: string }>(`/pages/${id}/retry-png`, {
        method: 'POST',
      }),
  },

  files: {
    list: (projectId: string) =>
      request<ProjectFileFlat[]>(`/projects/${projectId}/files`),
    tree: (projectId: string) =>
      request<ProjectFileTree[]>(`/projects/${projectId}/files/tree`),
    create: (projectId: string, data: {
      name: string;
      fileType: string;
      storagePath?: string;
      pageCount?: number;
      isFolder?: boolean;
      parentId?: string;
    }) => request<ProjectFileFlat>(`/projects/${projectId}/files`, {
      method: 'POST',
      body: data,
    }),
    get: (fileId: string) => request<ProjectFileFlat>(`/files/${fileId}`),
    update: (fileId: string, data: { name?: string; storagePath?: string; pageCount?: number }) =>
      request<ProjectFileFlat>(`/files/${fileId}`, { method: 'PATCH', body: data }),
    delete: (fileId: string) => request<void>(`/files/${fileId}`, { method: 'DELETE' }),
  },

  pointers: {
    list: (pageId: string, signal?: AbortSignal) => {
      return request<PointerResponse[]>(`/pages/${pageId}/pointers`, { signal });
    },
    // Create pointer with AI analysis - just send bounding box
    create: (pageId: string, data: {
      bboxX: number;
      bboxY: number;
      bboxWidth: number;
      bboxHeight: number;
    }) => request<PointerResponse>(`/pages/${pageId}/pointers`, {
      method: 'POST',
      body: data,
    }),
    // Create pointer manually without AI - provide all fields
    createManual: (pageId: string, data: {
      title: string;
      description: string;
      bboxX: number;
      bboxY: number;
      bboxWidth: number;
      bboxHeight: number;
      textSpans?: string[];
      pngPath?: string;
    }) => request<PointerResponse>(`/pages/${pageId}/pointers/manual`, {
      method: 'POST',
      body: data,
    }),
    get: (pointerId: string) => request<PointerResponse>(`/pointers/${pointerId}`),
    update: (pointerId: string, data: { title?: string; description?: string }) =>
      request<PointerResponse>(`/pointers/${pointerId}`, { method: 'PATCH', body: data }),
    delete: (pointerId: string) => request<void>(`/pointers/${pointerId}`, { method: 'DELETE' }),
  },

  queries: {
    list: (projectId: string) =>
      request<QueryResponse[]>(`/projects/${projectId}/queries`),
    get: (queryId: string) => request<QueryResponse>(`/queries/${queryId}`),
    hide: (queryId: string) => request<void>(`/queries/${queryId}/hide`, { method: 'PATCH' }),
  },

  conversations: {
    list: (projectId: string) =>
      request<ConversationResponse[]>(`/projects/${projectId}/conversations`),
    create: (projectId: string) =>
      request<ConversationResponse>(`/projects/${projectId}/conversations`, { method: 'POST' }),
    get: (conversationId: string) =>
      request<ConversationWithQueriesResponse>(`/conversations/${conversationId}`),
    delete: (conversationId: string) =>
      request<void>(`/conversations/${conversationId}`, { method: 'DELETE' }),
  },

  processing: {
    processUploads: (projectId: string) =>
      request<ProcessUploadsResult>(`/projects/${projectId}/process-uploads`, { method: 'POST' }),
  },
};

export { ApiError };
