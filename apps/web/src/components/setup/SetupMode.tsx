import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { FolderTree } from './FolderTree';
import { PdfViewer } from './PdfViewer';
import { ContextPanel, PanelView } from './context-panel';
import { UploadProgressModal } from './UploadProgressModal';
import { ModeToggle } from '../ModeToggle';
import { CollapsiblePanel } from '../ui/CollapsiblePanel';
import { AppMode, ContextPointer, ProjectFile, FileType, ProjectHierarchy } from '../../types';
import { Upload, Plus, BrainCircuit, FolderOpen, Layers, X, Loader2, Trash2 } from 'lucide-react';
import { api, DisciplineWithPagesResponse } from '../../lib/api';
import { downloadFile, blobToFile, uploadFile } from '../../lib/storage';
import { buildUploadPlan, planToApiRequest } from '../../lib/disciplineClassifier';
import { usePagePointersAsContext, useCreatePointer, useDeletePointer, toContextPointer } from '../../hooks/usePointers';
import { DriveImportButton, DriveImportFile } from './DriveImportButton';
import { DisciplineCode, getDisciplineDisplayName } from '../../lib/disciplineClassifier';

// Types for setup mode state persistence
interface SetupState {
  selectedFileId: string | null;
  selectedPointerId: string | null;
  isDrawingEnabled: boolean;
  expandedNodes: string[];  // Mind map expanded state
}

interface SetupModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
  localFileMapRef: React.MutableRefObject<Map<string, File>>;
  setupState: SetupState;
  setSetupState: React.Dispatch<React.SetStateAction<SetupState>>;
}

export const SetupMode: React.FC<SetupModeProps> = ({
  mode,
  setMode,
  projectId,
  localFileMapRef,
  setupState,
  setSetupState,
}) => {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null);

  // Use lifted state from props (but keep local versions for smooth updates)
  const selectedPointerId = setupState.selectedPointerId;
  const isDrawingEnabled = setupState.isDrawingEnabled;

  const setSelectedPointerId = (id: string | null) => {
    setSetupState(prev => ({ ...prev, selectedPointerId: id }));
  };
  const setIsDrawingEnabled = (enabled: boolean) => {
    setSetupState(prev => ({ ...prev, isDrawingEnabled: enabled }));
  };
  const expandedNodes = setupState.expandedNodes;
  const setExpandedNodes = (updater: string[] | ((prev: string[]) => string[])) => {
    if (typeof updater === 'function') {
      setSetupState(prev => ({ ...prev, expandedNodes: updater(prev.expandedNodes) }));
    } else {
      setSetupState(prev => ({ ...prev, expandedNodes: updater }));
    }
  };
  const [uploadedFiles, setUploadedFiles] = useState<ProjectFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(true);
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [fileLoadError, setFileLoadError] = useState<string | null>(null);
  const [isDeleteMode, setIsDeleteMode] = useState(false);
  const [selectedForDeletion, setSelectedForDeletion] = useState<Set<string>>(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [hierarchyRefresh, setHierarchyRefresh] = useState(0);
  const [hierarchy, setHierarchy] = useState<ProjectHierarchy | null>(null);
  // Pipeline progress with 2 progress bars (upload + PNG rendering)
  const [uploadProgress, setUploadProgress] = useState<{
    upload: { current: number; total: number };
    png: { current: number; total: number };
  } | null>(null);
  const [showProgressModal, setShowProgressModal] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [pngStageComplete, setPngStageComplete] = useState(false);
  const [failedPageIds, setFailedPageIds] = useState<Set<string>>(new Set());
  const [panelView, setPanelView] = useState<PanelView>({ type: 'mindmap' });
  const [highlightedPointer, setHighlightedPointer] = useState<{
    bounds: { x: number; y: number; w: number; h: number };
  } | null>(null);
  const [focusPointerId, setFocusPointerId] = useState<string | null>(null);
  // Track sidebar widths for visible-area centering
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(288);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(400);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const updateTimeoutRef = useRef<Record<string, NodeJS.Timeout>>({});
  // Note: localFileMapRef is now passed as a prop from App.tsx to persist across mode switches

  // Get pointers from React Query cache (single source of truth)
  const pageId = selectedFile?.type !== FileType.FOLDER ? selectedFile?.id ?? null : null;
  const { data: pointers = [], isLoading: isLoadingPointers } = usePagePointersAsContext(pageId);

  // Mutations for creating/deleting pointers
  const createPointerMutation = useCreatePointer(projectId);
  const deletePointerMutation = useDeletePointer(projectId);

  // Convert discipline hierarchy to ProjectFile format for tree display
  const convertDisciplinesToProjectFiles = (
    disciplines: DisciplineWithPagesResponse[],
    hierarchyData?: ProjectHierarchy | null
  ): ProjectFile[] => {
    // Build a map of page ID -> pointer count from hierarchy if available
    const pointerCountMap = new Map<string, number>();
    if (hierarchyData) {
      for (const disc of hierarchyData.disciplines) {
        for (const page of disc.pages) {
          pointerCountMap.set(page.id, page.pointerCount);
        }
      }
    }

    return disciplines.map(disc => ({
      id: disc.id,
      name: disc.displayName,
      type: FileType.FOLDER,
      parentId: undefined,
      storagePath: undefined,
      children: disc.pages.map(page => ({
        id: page.id,
        name: page.pageName,
        type: FileType.PDF,
        parentId: disc.id,
        storagePath: page.filePath,
        pointerCount: pointerCountMap.get(page.id) ?? 0,
        children: undefined,
      })),
    }));
  };

  // Helper to find a file by ID in the tree
  const findFileById = (files: ProjectFile[], id: string): ProjectFile | null => {
    for (const file of files) {
      if (file.id === id) return file;
      if (file.children) {
        const found = findFileById(file.children, id);
        if (found) return found;
      }
    }
    return null;
  };

  // Helper to find discipline ID for a given page ID
  const findDisciplineIdForPage = useCallback((pageId: string): string | null => {
    if (!hierarchy) return null;
    for (const disc of hierarchy.disciplines) {
      if (disc.pages.some(p => p.id === pageId)) {
        return disc.id;
      }
    }
    return null;
  }, [hierarchy]);

  // Clear focus pointer ID after scroll completes
  const handleFocusComplete = useCallback(() => {
    setFocusPointerId(null);
  }, []);

  // Sync selectedFileId to parent when selection changes
  const handleFileSelect = (file: ProjectFile) => {
    setSelectedFile(file);
    setSetupState(prev => ({ ...prev, selectedFileId: file.id }));
  };

  // Load hierarchy and files together on mount (hierarchy first for pointer counts)
  // Delay loading if upload is in progress and PNG stage hasn't completed
  useEffect(() => {
    // Skip loading if upload is in progress and PNG stage isn't complete
    if (showProgressModal && !pngStageComplete) {
      return;
    }

    async function loadFilesWithHierarchy() {
      try {
        setIsLoadingFiles(true);

        // Load hierarchy FIRST (has pointer counts)
        const hierarchyData = await api.projects.getHierarchy(projectId);
        setHierarchy(hierarchyData);

        // Then load file structure with counts from hierarchy
        const response = await api.projects.getFull(projectId);
        const convertedFiles = convertDisciplinesToProjectFiles(response.disciplines, hierarchyData);
        setUploadedFiles(sortFiles(convertedFiles));

        // Restore file selection if we have a saved selectedFileId
        if (setupState.selectedFileId && !selectedFile) {
          const foundFile = findFileById(convertedFiles, setupState.selectedFileId);
          if (foundFile) {
            setSelectedFile(foundFile);
          }
        }
      } catch (err) {
        console.error('Failed to load files:', err);
        // Project might not have any disciplines yet - that's OK
        setUploadedFiles([]);
      } finally {
        setIsLoadingFiles(false);
      }
    }
    loadFilesWithHierarchy();
  }, [projectId, pngStageComplete, showProgressModal]);

  // Refresh hierarchy when hierarchyRefresh changes (after uploads, etc.)
  useEffect(() => {
    if (hierarchyRefresh === 0) return; // Skip initial mount (already loaded above)

    async function refreshHierarchy() {
      try {
        const data = await api.projects.getHierarchy(projectId);
        setHierarchy(data);
      } catch (err) {
        console.error('Failed to refresh hierarchy:', err);
      }
    }
    refreshHierarchy();
  }, [projectId, hierarchyRefresh]);

  // Sync pointer counts from hierarchy to uploadedFiles when hierarchy changes
  useEffect(() => {
    if (!hierarchy || uploadedFiles.length === 0) return;

    // Build pointer count map
    const pointerCountMap = new Map<string, number>();
    for (const disc of hierarchy.disciplines) {
      for (const page of disc.pages) {
        pointerCountMap.set(page.id, page.pointerCount);
      }
    }

    // Update uploadedFiles with pointer counts
    const updatePointerCounts = (files: ProjectFile[]): ProjectFile[] => {
      return files.map(f => {
        const updated = { ...f };
        if (f.type !== FileType.FOLDER && pointerCountMap.has(f.id)) {
          updated.pointerCount = pointerCountMap.get(f.id);
        }
        if (f.children) {
          updated.children = updatePointerCounts(f.children);
        }
        return updated;
      });
    };

    setUploadedFiles(prev => updatePointerCounts(prev));
  }, [hierarchy]);

  // Fetch file from storage when page is selected
  useEffect(() => {
    if (!selectedFile || selectedFile.file || selectedFile.type === FileType.FOLDER) {
      setFileLoadError(null);
      setIsLoadingFile(false);
      return;
    }

    async function fetchFile() {
      try {
        setIsLoadingFile(true);
        setFileLoadError(null);

        // First check if we have it in local memory (from current session upload)
        const localFile = localFileMapRef.current.get(selectedFile.id);
        if (localFile) {
          // Update the selectedFile with the File object
          setSelectedFile(prev => prev ? { ...prev, file: localFile } : null);

          // Also update in the tree
          setUploadedFiles(prev => updateFileInTree(prev, selectedFile.id, { file: localFile }));
          setIsLoadingFile(false);
          return;
        }

        // Otherwise, try to fetch from storage (for previously uploaded files)
        // Use the storagePath from the ProjectFile if available, or fetch page info
        let storagePath = selectedFile.storagePath;
        if (!storagePath) {
          const pageInfo = await api.pages.get(selectedFile.id);
          storagePath = pageInfo.filePath;
        }

        if (storagePath) {
          const blob = await downloadFile(storagePath);
          const file = blobToFile(blob, selectedFile.name);

          // Update the selectedFile with the File object
          setSelectedFile(prev => prev ? { ...prev, file, storagePath } : null);

          // Also update in the tree
          setUploadedFiles(prev => updateFileInTree(prev, selectedFile.id, { file, storagePath }));
        } else {
          // Page exists in DB but not uploaded to storage
          setFileLoadError('File not found in cloud storage. This may happen if the browser was refreshed during upload. Please re-upload the file.');
        }
      } catch (err) {
        console.error('Failed to fetch file:', err);
        setFileLoadError('Failed to load file. Please try again.');
      } finally {
        setIsLoadingFile(false);
      }
    }
    fetchFile();
  }, [selectedFile?.id]);

  // Helper to update a file in the tree structure
  const updateFileInTree = (files: ProjectFile[], fileId: string, updates: Partial<ProjectFile>): ProjectFile[] => {
    return files.map(f => {
      if (f.id === fileId) {
        return { ...f, ...updates };
      }
      if (f.children) {
        return { ...f, children: updateFileInTree(f.children, fileId, updates) };
      }
      return f;
    });
  };

  // Update pointer with debounced API call
  const updatePointer = useCallback((id: string, updates: Partial<ContextPointer>) => {
    // Clear existing timeout for this pointer
    if (updateTimeoutRef.current[id]) {
      clearTimeout(updateTimeoutRef.current[id]);
    }

    // Debounce API call - React Query will handle cache invalidation
    updateTimeoutRef.current[id] = setTimeout(async () => {
      try {
        await api.pointers.update(id, {
          title: updates.title,
          description: updates.description,
        });
        // Invalidate cache to refresh the pointer data
        queryClient.invalidateQueries({ queryKey: ['pointers', pageId] });
      } catch (err) {
        console.error('Failed to update pointer:', err);
      }
    }, 300);
  }, [pageId, queryClient]);

  // Handle highlighting a pointer (from context panel)
  const handleHighlightPointer = useCallback(async (pointerId: string) => {
    try {
      const pointer = await api.pointers.get(pointerId);
      setHighlightedPointer({
        bounds: {
          x: pointer.bboxX,
          y: pointer.bboxY,
          w: pointer.bboxWidth,
          h: pointer.bboxHeight,
        },
      });
      // Also select the pointer
      setSelectedPointerId(pointerId);
    } catch (err) {
      console.error('Failed to load pointer for highlighting:', err);
    }
  }, []);

  // Clear highlight when panel view changes to something other than pointer
  useEffect(() => {
    if (panelView.type !== 'pointer') {
      setHighlightedPointer(null);
    }
  }, [panelView.type]);

  // Navigate to a page from context panel
  const handleNavigateToPage = useCallback((pageId: string) => {
    const file = findFileById(uploadedFiles, pageId);
    if (file) {
      handleFileSelect(file);
    }
  }, [uploadedFiles]);

  // Delete pointer - uses mutation with optimistic update
  const deletePointer = useCallback((id: string) => {
    if (selectedPointerId === id) {
      setSelectedPointerId(null);
    }

    // Use the mutation - it handles optimistic updates and cache invalidation
    deletePointerMutation.mutate({
      pointerId: id,
      pageId: pageId!,
    });
  }, [selectedPointerId, deletePointerMutation, pageId]);

  // Create pointer via API (with AI analysis) - uses mutation with optimistic UI
  const handlePointerCreate = useCallback(async (data: {
    pageNumber: number;
    bounds: { xNorm: number; yNorm: number; wNorm: number; hNorm: number };
  }): Promise<ContextPointer | null> => {
    if (!selectedFile || !pageId) return null;

    const tempId = `temp-${crypto.randomUUID()}`;

    try {
      const result = await createPointerMutation.mutateAsync({
        pageId,
        bounds: {
          bboxX: data.bounds.xNorm,
          bboxY: data.bounds.yNorm,
          bboxWidth: data.bounds.wNorm,
          bboxHeight: data.bounds.hNorm,
        },
        tempId,
        onCreated: (created) => {
          // Select the new pointer
          setSelectedPointerId(created.id);

          // Auto-expand path to new pointer in mind map
          const disciplineId = findDisciplineIdForPage(pageId);
          if (disciplineId && hierarchy) {
            const projectNodeId = `project-${hierarchy.name}`;
            setExpandedNodes(prev => {
              const newSet = new Set(prev);
              newSet.add(projectNodeId);
              newSet.add(disciplineId);
              newSet.add(pageId);
              return Array.from(newSet);
            });
          }

          // Signal to scroll/center on the new pointer
          setFocusPointerId(created.id);

          // Refresh hierarchy to update file tree pointer counts
          setHierarchyRefresh(h => h + 1);
        },
      });

      // Convert API response to ContextPointer
      return toContextPointer(result);
    } catch (err) {
      console.error('Failed to create pointer:', err);
      return null;
    }
  }, [selectedFile, pageId, hierarchy, findDisciplineIdForPage, setExpandedNodes, createPointerMutation]);

  const getFileType = (filename: string): FileType | null => {
    const ext = filename.toLowerCase().split('.').pop();
    switch (ext) {
      case 'pdf': return FileType.PDF;
      case 'csv': return FileType.CSV;
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
      case 'webp': return FileType.IMAGE;
      default: return null; // Unknown/unsupported file type
    }
  };

  // Check if a file should be skipped (system files, hidden files, etc.)
  const shouldSkipFile = (filename: string): boolean => {
    const name = filename.toLowerCase();
    // Skip hidden files (starting with .)
    if (name.startsWith('.')) return true;
    // Skip common system files
    const skipFiles = ['thumbs.db', 'desktop.ini', '.ds_store'];
    if (skipFiles.includes(name)) return true;
    // Skip files without supported extensions
    return getFileType(filename) === null;
  };

  const sortFiles = (files: ProjectFile[]): ProjectFile[] => {
    return files.sort((a, b) => {
      // Folders first, then files
      const aIsFolder = a.type === FileType.FOLDER;
      const bIsFolder = b.type === FileType.FOLDER;
      if (aIsFolder && !bIsFolder) return -1;
      if (!aIsFolder && bIsFolder) return 1;
      // Alphabetically within each group
      return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    }).map(file => ({
      ...file,
      children: file.children ? sortFiles(file.children) : undefined
    }));
  };

  // Get all descendant IDs for a file/folder (for cascading selection)
  const getAllDescendantIds = useCallback((fileId: string, files: ProjectFile[]): string[] => {
    const ids: string[] = [];

    const findAndCollect = (nodes: ProjectFile[]): boolean => {
      for (const node of nodes) {
        if (node.id === fileId) {
          // Found the target, collect all descendants
          const collectDescendants = (n: ProjectFile) => {
            if (n.children) {
              for (const child of n.children) {
                ids.push(child.id);
                collectDescendants(child);
              }
            }
          };
          collectDescendants(node);
          return true;
        }
        if (node.children && findAndCollect(node.children)) {
          return true;
        }
      }
      return false;
    };

    findAndCollect(files);
    return ids;
  }, []);

  // Toggle file selection (with cascading for folders)
  const toggleFileSelection = useCallback((fileId: string) => {
    setSelectedForDeletion(prev => {
      const newSet = new Set(prev);
      const descendantIds = getAllDescendantIds(fileId, uploadedFiles);

      if (newSet.has(fileId)) {
        // Deselect file and all descendants
        newSet.delete(fileId);
        descendantIds.forEach(id => newSet.delete(id));
      } else {
        // Select file and all descendants
        newSet.add(fileId);
        descendantIds.forEach(id => newSet.add(id));
      }

      return newSet;
    });
  }, [getAllDescendantIds, uploadedFiles]);

  // Handle delete confirmation
  const handleDeleteConfirm = useCallback(async () => {
    if (selectedForDeletion.size === 0) return;

    setIsDeleting(true);
    try {
      // Find root selections (not descendants of other selections)
      const rootSelections = Array.from(selectedForDeletion as Set<string>).filter((id: string) => {
        // Check if any ancestor is also selected
        const isDescendant = (nodes: ProjectFile[], targetId: string, ancestorSelected: boolean): boolean => {
          for (const node of nodes) {
            const nodeSelected = selectedForDeletion.has(node.id);
            if (node.id === targetId) {
              return ancestorSelected;
            }
            if (node.children) {
              if (isDescendant(node.children, targetId, ancestorSelected || nodeSelected)) {
                return true;
              }
            }
          }
          return false;
        };
        return !isDescendant(uploadedFiles, id, false);
      });

      // Delete each root selection
      // Disciplines are "folders", pages are "files"
      for (const itemId of rootSelections) {
        const item = findFileById(uploadedFiles, itemId);
        if (!item) continue;

        if (item.type === FileType.FOLDER) {
          // This is a discipline - delete it (cascades to pages)
          await api.disciplines.delete(itemId);
        } else {
          // This is a page
          await api.pages.delete(itemId);
        }
        // Clean up local file map
        localFileMapRef.current.delete(itemId);
      }

      // Clear selected file if it was deleted
      if (selectedFile && selectedForDeletion.has(selectedFile.id)) {
        setSelectedFile(null);
        // Pointers will be cleared automatically since pageId becomes null
      }

      // Reload disciplines and pages
      const response = await api.projects.getFull(projectId);
      setUploadedFiles(sortFiles(convertDisciplinesToProjectFiles(response.disciplines)));

      // Reset delete mode
      setSelectedForDeletion(new Set());
      setIsDeleteMode(false);
      setShowDeleteModal(false);
    } catch (err) {
      console.error('Failed to delete:', err);
      alert('Failed to delete some items. Please try again.');
    } finally {
      setIsDeleting(false);
    }
  }, [selectedForDeletion, uploadedFiles, selectedFile, projectId]);

  // Cancel delete mode
  const cancelDeleteMode = useCallback(() => {
    setIsDeleteMode(false);
    setSelectedForDeletion(new Set());
  }, []);

  // Retry PNG rendering for a failed page
  const handleRetryPng = useCallback(async (pageId: string) => {
    try {
      const result = await api.pages.retryPng(pageId);
      if (result.success) {
        // Remove from failed set
        setFailedPageIds(prev => {
          const next = new Set(prev);
          next.delete(pageId);
          return next;
        });
        // Refresh hierarchy to get updated pageImageReady status
        setHierarchyRefresh(prev => prev + 1);
      } else {
        console.error(`Retry PNG failed for page ${pageId}:`, result.error);
        alert(`Failed to re-render PNG: ${result.error}`);
      }
    } catch (err) {
      console.error(`Retry PNG error for page ${pageId}:`, err);
      alert('Failed to retry PNG rendering. Please try again.');
    }
  }, []);

  const handleFolderUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsUploading(true);
    setUploadError(null);
    let sseTimeoutId: ReturnType<typeof setTimeout> | undefined;

    try {
      // Build upload plan using discipline classifier
      const plan = buildUploadPlan(files);

      if (plan.totalFileCount === 0) {
        alert('No PDF files found in the selected folder.');
        setIsUploading(false);
        return;
      }

      // Show warning if files need review (for now, just proceed with best guess)
      if (plan.filesNeedingReview.length > 0) {
        console.log(`${plan.filesNeedingReview.length} files need discipline review`);
      }

      // Initialize progress and show modal (only upload + PNG rendering)
      const totalFiles = plan.totalFileCount;
      setUploadProgress({
        upload: { current: 0, total: totalFiles },
        png: { current: 0, total: totalFiles },
      });
      setShowProgressModal(true);
      setPngStageComplete(false); // Reset for new upload
      setFailedPageIds(new Set()); // Clear previous failures

      // Track uploaded file paths
      const uploadedPaths = new Map<string, string>(); // relativePath -> storagePath

      // Collect all files to upload
      const filesToUpload: Array<{ file: File; relativePath: string }> = [];
      for (const [_disciplineCode, classifiedFiles] of plan.disciplines) {
        for (const cf of classifiedFiles) {
          filesToUpload.push({ file: cf.file, relativePath: cf.relativePath });
        }
      }

      // Parallel upload with concurrency limit of 5
      const MAX_CONCURRENT = 5;
      const semaphore = new Set<Promise<void>>();
      let uploadedCount = 0;

      for (const { file, relativePath } of filesToUpload) {
        const promise = (async () => {
          try {
            const uploadResult = await uploadFile(projectId, file, relativePath);
            uploadedPaths.set(relativePath, uploadResult.storagePath);
            // Store file in memory for immediate viewing
            localFileMapRef.current.set(relativePath, file);
          } catch (uploadErr) {
            console.error(`Failed to upload ${file.name} to storage:`, uploadErr);
          } finally {
            uploadedCount++;
            setUploadProgress(prev => prev ? {
              ...prev,
              upload: { current: uploadedCount, total: totalFiles },
            } : null);
          }
        })();

        semaphore.add(promise);
        promise.finally(() => semaphore.delete(promise));

        if (semaphore.size >= MAX_CONCURRENT) {
          await Promise.race(semaphore);
        }
      }
      // Wait for remaining uploads
      await Promise.all(semaphore);

      // Build API request from plan (will be sent to SSE endpoint for bulk insert)
      const apiRequest = planToApiRequest(plan, uploadedPaths);

      setIsUploading(false);

      // Start processing pipeline via SSE (bulk insert → PNG → complete)
      // Backend will bulk insert disciplines/pages, then render PNGs
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const API_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

      // Get auth token for SSE request
      const { data: { session } } = await (await import('../../lib/supabase')).supabase.auth.getSession();

      // Use AbortController for timeout (15 minutes for large uploads with OCR/AI processing)
      const controller = new AbortController();
      sseTimeoutId = setTimeout(() => {
        console.log('SSE processing timeout - aborting after 15 minutes');
        controller.abort();
      }, 900000); // 15 minute timeout

      // Send upload plan in POST body - backend will bulk insert disciplines/pages
      const sseResponse = await fetch(`${API_URL}/projects/${projectId}/process-uploads-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {}),
        },
        body: JSON.stringify({
          disciplines: apiRequest.disciplines.map(d => ({
            code: d.code,
            display_name: d.displayName,
            pages: d.pages.map(p => ({
              page_name: p.pageName,
              storage_path: p.storagePath,
            })),
          })),
        }),
        signal: controller.signal,
      });

      if (!sseResponse.ok) {
        const errorText = await sseResponse.text();
        console.error('SSE response error:', sseResponse.status, errorText);
        throw new Error(`Failed to start processing pipeline: ${sseResponse.status}`);
      }

      console.log('SSE connection established, reading stream...');

      // Read the SSE stream
      const reader = sseResponse.body?.getReader();
      const decoder = new TextDecoder();
      let receivedComplete = false;

      if (reader) {
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE events from buffer
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            // Skip heartbeat comments
            if (line.startsWith(':')) continue;

            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));

                // Handle new stage-based event format
                if (data.stage === 'init') {
                  // Backend has bulk-inserted disciplines/pages
                  console.log(`Processing ${data.pageCount} pages`);
                } else if (data.stage === 'png') {
                  setUploadProgress(prev => prev ? {
                    ...prev,
                    png: { current: data.current, total: data.total },
                  } : null);

                  // Mark PNG stage complete when finished - triggers file tree load
                  if (data.current === data.total && data.total > 0) {
                    setPngStageComplete(true);
                    setHierarchyRefresh(prev => prev + 1);
                  }
                } else if (data.stage === 'png_failures') {
                  // Some pages failed PNG rendering - track for retry UI
                  if (data.pageIds && data.pageIds.length > 0) {
                    console.warn(`PNG rendering failed for ${data.pageIds.length} pages:`, data.pageIds);
                    setFailedPageIds(new Set(data.pageIds));
                  }
                } else if (data.stage === 'complete') {
                  receivedComplete = true;
                  // Refresh hierarchy after processing
                  setHierarchyRefresh(prev => prev + 1);

                  // Auto-close modal after 1.5 seconds
                  setTimeout(() => {
                    setShowProgressModal(false);
                    setUploadProgress(null);
                  }, 1500);
                } else if (data.stage === 'error') {
                  setUploadError(data.message || 'An error occurred during processing');
                }
              } catch (parseErr) {
                console.error('Failed to parse SSE data:', parseErr);
              }
            }
          }
        }
      }

      // If stream closed without completion, log it but don't retry
      // (PNG stage is fast enough that retries aren't needed)
      if (!receivedComplete) {
        console.warn('SSE stream closed without receiving complete event');
        // Still close the modal after a delay - user can refresh if needed
        setTimeout(() => {
          setShowProgressModal(false);
          setUploadProgress(null);
        }, 1500);
      }

    } catch (err) {
      console.error('Failed to upload/process files:', err);
      // Log more details for debugging
      if (err instanceof Error) {
        console.error('Error name:', err.name, 'message:', err.message);
      }
      // Don't show alert for abort (timeout) - user can see progress stopped
      if (err instanceof Error && err.name !== 'AbortError') {
        setUploadError(err.message || 'Failed to upload files. Please try again.');
      }
    } finally {
      setIsUploading(false);
      // Clear the SSE timeout if it hasn't fired yet
      if (sseTimeoutId) {
        clearTimeout(sseTimeoutId);
      }
      // Reset input so the same folder can be selected again
      e.target.value = '';
    }
  };

  // Handle Drive imports (similar to folder upload but for pre-classified files)
  const handleDriveImport = async (importedFiles: DriveImportFile[]) => {
    if (importedFiles.length === 0) return;

    setIsUploading(true);
    setUploadError(null);
    let sseTimeoutId: ReturnType<typeof setTimeout> | undefined;

    try {
      const totalFiles = importedFiles.length;

      // Initialize progress and show modal
      setUploadProgress({
        upload: { current: 0, total: totalFiles },
        png: { current: 0, total: totalFiles },
      });
      setShowProgressModal(true);
      setPngStageComplete(false);
      setFailedPageIds(new Set());

      // Group files by discipline
      const disciplineMap = new Map<DisciplineCode, DriveImportFile[]>();
      for (const importedFile of importedFiles) {
        const existing = disciplineMap.get(importedFile.discipline) || [];
        existing.push(importedFile);
        disciplineMap.set(importedFile.discipline, existing);
      }

      // Track uploaded file paths
      const uploadedPaths = new Map<string, string>(); // relativePath -> storagePath

      // Upload files with concurrency limit
      const MAX_CONCURRENT = 5;
      const semaphore = new Set<Promise<void>>();
      let uploadedCount = 0;

      for (const importedFile of importedFiles) {
        // Generate a relative path: discipline/filename
        const relativePath = `${importedFile.discipline}/${importedFile.file.name}`;

        const promise = (async () => {
          try {
            const uploadResult = await uploadFile(projectId, importedFile.file, relativePath);
            uploadedPaths.set(relativePath, uploadResult.storagePath);
            // Store file in memory for immediate viewing
            localFileMapRef.current.set(relativePath, importedFile.file);
          } catch (uploadErr) {
            console.error(`Failed to upload ${importedFile.file.name} to storage:`, uploadErr);
          } finally {
            uploadedCount++;
            setUploadProgress(prev => prev ? {
              ...prev,
              upload: { current: uploadedCount, total: totalFiles },
            } : null);
          }
        })();

        semaphore.add(promise);
        promise.finally(() => semaphore.delete(promise));

        if (semaphore.size >= MAX_CONCURRENT) {
          await Promise.race(semaphore);
        }
      }
      await Promise.all(semaphore);

      // Build API request
      const disciplines: Array<{
        code: DisciplineCode;
        displayName: string;
        pages: Array<{ pageName: string; fileName: string; storagePath: string }>;
      }> = [];

      for (const [code, files] of disciplineMap) {
        const pages = files
          .map(f => {
            const relativePath = `${code}/${f.file.name}`;
            const storagePath = uploadedPaths.get(relativePath);
            if (!storagePath) return null;
            return {
              pageName: f.file.name.replace(/\.[^/.]+$/, ''),
              fileName: f.file.name,
              storagePath,
            };
          })
          .filter((p): p is NonNullable<typeof p> => p !== null);

        if (pages.length > 0) {
          disciplines.push({
            code,
            displayName: getDisciplineDisplayName(code),
            pages,
          });
        }
      }

      setIsUploading(false);

      // Start processing pipeline via SSE
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const API_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

      const { data: { session } } = await (await import('../../lib/supabase')).supabase.auth.getSession();

      const controller = new AbortController();
      sseTimeoutId = setTimeout(() => {
        console.log('SSE processing timeout - aborting after 15 minutes');
        controller.abort();
      }, 900000);

      const sseResponse = await fetch(`${API_URL}/projects/${projectId}/process-uploads-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {}),
        },
        body: JSON.stringify({
          disciplines: disciplines.map(d => ({
            code: d.code,
            display_name: d.displayName,
            pages: d.pages.map(p => ({
              page_name: p.pageName,
              storage_path: p.storagePath,
            })),
          })),
        }),
        signal: controller.signal,
      });

      if (!sseResponse.ok) {
        const errorText = await sseResponse.text();
        console.error('SSE response error:', sseResponse.status, errorText);
        throw new Error(`Failed to start processing pipeline: ${sseResponse.status}`);
      }

      // Read the SSE stream (reuse existing stream parsing logic)
      const reader = sseResponse.body?.getReader();
      const decoder = new TextDecoder();
      let receivedComplete = false;

      if (reader) {
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith(':')) continue;
            if (line.startsWith('data: ')) {
              try {
                const eventData = JSON.parse(line.slice(6));
                if (eventData.type === 'png_progress') {
                  setUploadProgress(prev => prev ? {
                    ...prev,
                    png: { current: eventData.current || 0, total: eventData.total || totalFiles },
                  } : null);
                } else if (eventData.type === 'png_failed') {
                  if (eventData.page_id) {
                    setFailedPageIds(prev => new Set([...prev, eventData.page_id]));
                  }
                } else if (eventData.type === 'complete') {
                  receivedComplete = true;
                  setPngStageComplete(true);
                }
              } catch (parseErr) {
                console.error('Failed to parse SSE event:', line, parseErr);
              }
            }
          }
        }
      }

      if (sseTimeoutId) clearTimeout(sseTimeoutId);

      // Refresh hierarchy
      await queryClient.invalidateQueries({ queryKey: ['projectHierarchy', projectId] });
      setHierarchyRefresh(prev => prev + 1);

    } catch (err) {
      console.error('Drive import error:', err);
      setUploadError(err instanceof Error ? err.message : 'Drive import failed');
    } finally {
      setIsUploading(false);
      if (sseTimeoutId) clearTimeout(sseTimeoutId);
    }
  };

  return (
    <div className="relative h-full w-full bg-gradient-radial-dark text-slate-200 overflow-hidden font-sans pt-safe">
      {/* Sidebar: File Tree (absolute positioned overlay) */}
      <CollapsiblePanel
        side="left"
        defaultWidth={288}
        minWidth={240}
        maxWidth={400}
        collapsedIcon={<FolderOpen size={20} />}
        collapsedLabel="Files"
        className="border-r border-slate-800/50 glass-panel"
        onWidthChange={setLeftSidebarWidth}
      >
        <div className="flex flex-col h-full">
          <div className="p-4 border-b border-white/5 space-y-3">
              <ModeToggle mode={mode} setMode={setMode} />
              <div>
                <h1 className="font-bold text-lg tracking-tight text-white">
                  Maestro<span className="text-cyan-400 drop-shadow-[0_0_8px_rgba(6,182,212,0.5)]">Super</span>
                </h1>
                <p className="text-xs text-slate-400">Setup Mode</p>
              </div>
          </div>

          {isDeleteMode ? (
            <div className="p-3 flex gap-2 border-b border-white/5">
              <button
                onClick={cancelDeleteMode}
                className="flex-1 bg-slate-700/50 hover:bg-slate-600/50 text-white text-xs py-2.5 rounded-lg flex justify-center items-center gap-1.5 font-medium transition-all border border-slate-600/30"
              >
                <X size={14} /> Cancel
              </button>
              <button
                onClick={() => selectedForDeletion.size > 0 && setShowDeleteModal(true)}
                disabled={selectedForDeletion.size === 0}
                className={`flex-1 text-xs py-2.5 rounded-lg flex justify-center items-center gap-1.5 font-medium transition-all ${
                  selectedForDeletion.size > 0
                    ? 'bg-red-600 hover:bg-red-500 text-white border border-red-500'
                    : 'bg-red-600/30 text-red-300/50 border border-red-500/30 cursor-not-allowed'
                }`}
              >
                <Trash2 size={14} />
                Delete{selectedForDeletion.size > 0 && ` (${selectedForDeletion.size})`}
              </button>
            </div>
          ) : (
            <div className="p-3 flex gap-2 border-b border-white/5">
              <button className="flex-1 btn-primary text-white text-xs py-2.5 rounded-lg flex justify-center items-center gap-1.5 font-medium">
                <Plus size={14} /> New Folder
              </button>
              <button className="flex-1 bg-slate-700/50 hover:bg-slate-600/50 text-white text-xs py-2.5 rounded-lg flex justify-center items-center gap-1.5 font-medium transition-all border border-slate-600/30">
                <Upload size={14} /> Add Files
              </button>
              <button
                onClick={() => setIsDeleteMode(true)}
                className="bg-slate-700/50 hover:bg-red-600/30 hover:border-red-500/50 text-slate-400 hover:text-red-400 text-xs py-2.5 px-3 rounded-lg flex justify-center items-center font-medium transition-all border border-slate-600/30"
              >
                <Trash2 size={14} />
              </button>
            </div>
          )}

          {isLoadingFiles ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
            </div>
          ) : (
            <FolderTree
              files={uploadedFiles}
              onFileSelect={handleFileSelect}
              selectedFileId={selectedFile?.id || null}
              expandToFileId={setupState.selectedFileId}
              isDeleteMode={isDeleteMode}
              selectedForDeletion={selectedForDeletion}
              onToggleSelection={toggleFileSelection}
              failedPageIds={failedPageIds}
              onRetryPng={handleRetryPng}
            />
          )}

          {/* Upload Prompts */}
          <div className="p-4 border-t border-white/5">
              <input
                ref={folderInputRef}
                type="file"
                className="hidden"
                onChange={handleFolderUpload}
                disabled={isUploading}
                {...{ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>}
              />
              <button
                onClick={() => folderInputRef.current?.click()}
                disabled={isUploading}
                className="w-full py-3.5 rounded-lg bg-gradient-to-r from-cyan-600/20 to-blue-600/20 border border-cyan-500/30 text-cyan-200 text-sm font-medium hover:border-cyan-400/50 hover:from-cyan-600/30 hover:to-blue-600/30 transition-all shadow-lg shadow-cyan-900/10 group disabled:opacity-50 disabled:cursor-not-allowed"
              >
                  {isUploading ? (
                    <span className="flex items-center justify-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Uploading...
                    </span>
                  ) : (
                    <span className="group-hover:drop-shadow-[0_0_8px_rgba(6,182,212,0.5)] transition-all">+ Upload Plans</span>
                  )}
              </button>
              <div className="mt-2">
                <DriveImportButton
                  disabled={isUploading}
                  onFilesSelected={handleDriveImport}
                />
              </div>
          </div>
        </div>
      </CollapsiblePanel>

      {/* Main Content (full width, sidebars overlay on top) */}
      <div className="w-full h-full flex flex-col blueprint-grid-dark">
         {/* PDF Viewer */}
         <div className="flex-1 relative overflow-hidden">
            {selectedFile ? (
                <PdfViewer
                    file={selectedFile.file}
                    fileId={selectedFile.id}
                    pointers={pointers}
                    selectedPointerId={selectedPointerId}
                    setSelectedPointerId={setSelectedPointerId}
                    isDrawingEnabled={isDrawingEnabled}
                    setIsDrawingEnabled={setIsDrawingEnabled}
                    onPointerCreate={handlePointerCreate}
                    isLoadingFile={isLoadingFile}
                    fileLoadError={fileLoadError}
                    highlightedBounds={highlightedPointer?.bounds}
                    refreshTrigger={hierarchyRefresh}
                    leftSidebarWidth={leftSidebarWidth}
                    rightSidebarWidth={rightSidebarWidth}
                />
            ) : (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 animate-fade-in">
                    <div className="p-6 rounded-2xl bg-slate-800/30 border border-slate-700/30 backdrop-blur-sm">
                      <BrainCircuit size={56} className="mb-4 mx-auto text-slate-600" />
                      <p className="text-slate-400 text-center">Select a file to begin<br/><span className="text-cyan-400/70">context extraction</span></p>
                    </div>
                </div>
            )}
         </div>

      </div>

      {/* Context Panel (absolute positioned overlay) */}
      <CollapsiblePanel
        side="right"
        defaultWidth={400}
        minWidth={320}
        maxWidth={600}
        collapsedIcon={<Layers size={20} />}
        collapsedLabel="Context"
        className="border-l border-slate-800/50 glass-panel"
        onWidthChange={setRightSidebarWidth}
      >
        <div className="flex flex-col h-full">
           <div className="p-4 border-b border-white/5">
              <h2 className="font-semibold text-slate-100 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-cyan-400 shadow-glow-cyan-sm"></div>
                Project Context
              </h2>
           </div>
           <div className="flex-1 overflow-hidden">
              <ContextPanel
                projectId={projectId}
                hierarchy={hierarchy}
                panelView={panelView}
                setPanelView={setPanelView}
                activePageId={selectedFile?.id}
                refreshTrigger={hierarchyRefresh}
                onNavigateToPage={handleNavigateToPage}
                onHighlightPointer={handleHighlightPointer}
                onPointerDelete={deletePointer}
                expandedNodes={expandedNodes}
                setExpandedNodes={setExpandedNodes}
                focusNodeId={focusPointerId}
                onFocusComplete={handleFocusComplete}
              />
           </div>
        </div>
      </CollapsiblePanel>

      {/* Upload Progress Modal */}
      <UploadProgressModal
        isOpen={showProgressModal}
        progress={uploadProgress ?? {
          upload: { current: 0, total: 0 },
          png: { current: 0, total: 0 },
        }}
        error={uploadError ?? undefined}
        onRetry={() => {
          setUploadError(null);
          setShowProgressModal(false);
          setUploadProgress(null);
        }}
      />

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-full bg-red-500/20">
                <Trash2 size={20} className="text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-white">Delete Files</h3>
            </div>
            <p className="text-slate-300 mb-6">
              Are you sure you want to delete {selectedForDeletion.size} item{selectedForDeletion.size !== 1 && 's'}?
              This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowDeleteModal(false)}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-sm font-medium transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirm}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 size={14} />
                    Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
