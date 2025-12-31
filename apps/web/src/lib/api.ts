import { supabase } from './supabase';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RequestOptions {
  method?: string;
  body?: unknown;
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body } = options;

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
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    // Handle FastAPI validation errors which return detail as an array
    let message = 'Request failed';
    if (Array.isArray(error.detail)) {
      message = error.detail.map((e: { loc?: string[]; msg?: string }) =>
        `${e.loc?.join('.')}: ${e.msg}`
      ).join(', ');
    } else if (typeof error.detail === 'string') {
      message = error.detail;
    }
    console.error('API Error:', response.status, error);
    throw new ApiError(response.status, message);
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
    update: (id: string, data: { name?: string; status?: string }) =>
      request<Project>(`/projects/${id}`, { method: 'PATCH', body: data }),
    delete: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
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
    list: (fileId: string, page?: number) => {
      const params = page !== undefined ? `?page=${page}` : '';
      return request<ContextPointerResponse[]>(`/files/${fileId}/pointers${params}`);
    },
    create: (fileId: string, data: {
      pageNumber: number;
      bounds: Bounds;
      title?: string;
      description?: string;
    }) => request<ContextPointerResponse>(`/files/${fileId}/pointers`, {
      method: 'POST',
      body: data,
    }),
    get: (pointerId: string) => request<ContextPointerResponse>(`/pointers/${pointerId}`),
    update: (pointerId: string, data: { title?: string; description?: string }) =>
      request<ContextPointerResponse>(`/pointers/${pointerId}`, { method: 'PATCH', body: data }),
    delete: (pointerId: string) => request<void>(`/pointers/${pointerId}`, { method: 'DELETE' }),
    commit: (pointerId: string) =>
      request<ContextPointerResponse>(`/pointers/${pointerId}/commit`, { method: 'POST' }),
  },
};

export { ApiError };
