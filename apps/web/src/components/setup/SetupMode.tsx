import React, { useState, useRef, useEffect, useCallback } from 'react';
import { FolderTree } from './FolderTree';
import { PdfViewer } from './PdfViewer';
import { ModeToggle } from '../ModeToggle';
import { CollapsiblePanel } from '../ui/CollapsiblePanel';
import { AppMode, ContextPointer, ProjectFile, FileType } from '../../types';
import { Upload, Plus, BrainCircuit, FolderOpen, Layers, X, Loader2, Trash2 } from 'lucide-react';
import { api, DisciplineWithPagesResponse } from '../../lib/api';
import { downloadFile, blobToFile, uploadFile } from '../../lib/storage';
import { buildUploadPlan, planToApiRequest } from '../../lib/disciplineClassifier';

// Types for setup mode state persistence
interface SetupState {
  selectedFileId: string | null;
  selectedPointerId: string | null;
  activeTool: 'select' | 'rect' | 'text';
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
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null);
  const [pointers, setPointers] = useState<ContextPointer[]>([]);

  // Use lifted state from props (but keep local versions for smooth updates)
  const selectedPointerId = setupState.selectedPointerId;
  const activeTool = setupState.activeTool;

  const setSelectedPointerId = (id: string | null) => {
    setSetupState(prev => ({ ...prev, selectedPointerId: id }));
  };
  const setActiveTool = (tool: 'select' | 'rect' | 'text') => {
    setSetupState(prev => ({ ...prev, activeTool: tool }));
  };
  const [uploadedFiles, setUploadedFiles] = useState<ProjectFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(true);
  const [isLoadingPointers, setIsLoadingPointers] = useState(false);
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [fileLoadError, setFileLoadError] = useState<string | null>(null);
  const [isDeleteMode, setIsDeleteMode] = useState(false);
  const [selectedForDeletion, setSelectedForDeletion] = useState<Set<string>>(new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const contextPanelRef = useRef<HTMLDivElement>(null);
  const updateTimeoutRef = useRef<Record<string, NodeJS.Timeout>>({});
  // Note: localFileMapRef is now passed as a prop from App.tsx to persist across mode switches

  // Convert discipline hierarchy to ProjectFile format for tree display
  const convertDisciplinesToProjectFiles = (
    disciplines: DisciplineWithPagesResponse[]
  ): ProjectFile[] => {
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

  // Sync selectedFileId to parent when selection changes
  const handleFileSelect = (file: ProjectFile) => {
    setSelectedFile(file);
    setSetupState(prev => ({ ...prev, selectedFileId: file.id }));
  };

  // Load disciplines and pages from backend on mount
  useEffect(() => {
    async function loadFiles() {
      try {
        setIsLoadingFiles(true);
        const response = await api.projects.getFull(projectId);
        const convertedFiles = convertDisciplinesToProjectFiles(response.disciplines);
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
    loadFiles();
  }, [projectId]);

  // Load pointers when page is selected
  useEffect(() => {
    if (!selectedFile || selectedFile.type === FileType.FOLDER) {
      setPointers([]);
      return;
    }

    async function loadPointers() {
      try {
        setIsLoadingPointers(true);
        const pointerList = await api.pointers.list(selectedFile.id);
        setPointers(pointerList.map(p => ({
          id: p.id,
          pageId: p.pageId,
          title: p.title,
          description: p.description,
          textSpans: p.textSpans,
          bboxX: p.bboxX,
          bboxY: p.bboxY,
          bboxWidth: p.bboxWidth,
          bboxHeight: p.bboxHeight,
          pngPath: p.pngPath,
          hasEmbedding: p.hasEmbedding,
        })));
      } catch (err) {
        console.error('Failed to load pointers:', err);
        setPointers([]);
      } finally {
        setIsLoadingPointers(false);
      }
    }
    loadPointers();
  }, [selectedFile?.id]);

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
    // Update local state immediately
    setPointers(prev => prev.map(p => p.id === id ? { ...p, ...updates } : p));

    // Clear existing timeout for this pointer
    if (updateTimeoutRef.current[id]) {
      clearTimeout(updateTimeoutRef.current[id]);
    }

    // Debounce API call
    updateTimeoutRef.current[id] = setTimeout(async () => {
      try {
        await api.pointers.update(id, {
          title: updates.title,
          description: updates.description,
        });
      } catch (err) {
        console.error('Failed to update pointer:', err);
      }
    }, 300);
  }, []);

  // Delete pointer with API call
  const deletePointer = useCallback(async (id: string) => {
    // Update local state immediately
    setPointers(prev => prev.filter(p => p.id !== id));
    if (selectedPointerId === id) {
      setSelectedPointerId(null);
    }

    // Call API
    try {
      await api.pointers.delete(id);
    } catch (err) {
      console.error('Failed to delete pointer:', err);
    }
  }, [selectedPointerId]);

  // Create pointer via API
  const handlePointerCreate = useCallback(async (data: {
    pageNumber: number;
    bounds: { xNorm: number; yNorm: number; wNorm: number; hNorm: number };
  }): Promise<ContextPointer | null> => {
    if (!selectedFile) return null;

    try {
      const created = await api.pointers.create(selectedFile.id, {
        title: 'New Context',
        description: 'Add description...',
        bboxX: data.bounds.xNorm,
        bboxY: data.bounds.yNorm,
        bboxWidth: data.bounds.wNorm,
        bboxHeight: data.bounds.hNorm,
      });

      return {
        id: created.id,
        pageId: created.pageId,
        title: created.title,
        description: created.description,
        textSpans: created.textSpans,
        bboxX: created.bboxX,
        bboxY: created.bboxY,
        bboxWidth: created.bboxWidth,
        bboxHeight: created.bboxHeight,
        pngPath: created.pngPath,
        hasEmbedding: created.hasEmbedding,
      };
    } catch (err) {
      console.error('Failed to create pointer:', err);
      return null;
    }
  }, [selectedFile?.id]);

  // Scroll selected pointer block to center of panel
  useEffect(() => {
    if (!selectedPointerId || !contextPanelRef.current) return;

    const container = contextPanelRef.current;
    const selectedElement = container.querySelector(`[data-pointer-id="${selectedPointerId}"]`) as HTMLElement;

    if (selectedElement) {
      const containerHeight = container.clientHeight;
      const elementTop = selectedElement.offsetTop;
      const elementHeight = selectedElement.offsetHeight;

      // Calculate scroll position to center the element
      const scrollTo = elementTop - (containerHeight / 2) + (elementHeight / 2);

      container.scrollTo({
        top: Math.max(0, scrollTo),
        behavior: 'smooth'
      });
    }
  }, [selectedPointerId]);

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
        setPointers([]);
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

  const handleFolderUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsUploading(true);

    try {
      // Build upload plan using discipline classifier
      const plan = buildUploadPlan(files);

      if (plan.totalFileCount === 0) {
        alert('No PDF files found in the selected folder.');
        return;
      }

      // Show warning if files need review (for now, just proceed with best guess)
      if (plan.filesNeedingReview.length > 0) {
        console.log(`${plan.filesNeedingReview.length} files need discipline review`);
      }

      // Track uploaded file paths
      const uploadedPaths = new Map<string, string>(); // relativePath -> storagePath

      // Upload all files to Supabase Storage
      for (const [_disciplineCode, classifiedFiles] of plan.disciplines) {
        for (const cf of classifiedFiles) {
          try {
            const uploadResult = await uploadFile(projectId, cf.file, cf.relativePath);
            uploadedPaths.set(cf.relativePath, uploadResult.storagePath);
            // Store file in memory for immediate viewing
            localFileMapRef.current.set(cf.relativePath, cf.file);
          } catch (uploadErr) {
            console.error(`Failed to upload ${cf.fileName} to storage:`, uploadErr);
          }
        }
      }

      // Build API request from plan
      const apiRequest = planToApiRequest(plan, uploadedPaths);

      // Track relativePath -> pageId for file map updates
      const relativePathToPageId = new Map<string, string>();

      // Create disciplines and pages for each discipline
      for (const discData of apiRequest.disciplines) {
        // Create discipline
        const discipline = await api.disciplines.create(projectId, {
          name: discData.code,
          displayName: discData.displayName,
        });

        // Create pages for this discipline
        for (const pageData of discData.pages) {
          const page = await api.pages.create(discipline.id, {
            pageName: pageData.pageName,
            filePath: pageData.storagePath,
          });

          // Find the relative path that corresponds to this storage path
          for (const [relativePath, storagePath] of uploadedPaths.entries()) {
            if (storagePath === pageData.storagePath) {
              relativePathToPageId.set(relativePath, page.id);
              break;
            }
          }
        }
      }

      // Update local file map: move files from relativePath keys to pageId keys
      for (const [relativePath, pageId] of relativePathToPageId.entries()) {
        const file = localFileMapRef.current.get(relativePath);
        if (file) {
          localFileMapRef.current.delete(relativePath);
          localFileMapRef.current.set(pageId, file);
        }
      }

      // Reload disciplines and pages from backend
      const response = await api.projects.getFull(projectId);
      setUploadedFiles(sortFiles(convertDisciplinesToProjectFiles(response.disciplines)));

    } catch (err) {
      console.error('Failed to upload files:', err);
      alert('Failed to upload files. Please try again.');
    } finally {
      setIsUploading(false);
      // Reset input so the same folder can be selected again
      e.target.value = '';
    }
  };

  return (
    <div className="relative flex h-screen w-full bg-gradient-radial-dark text-slate-200 overflow-hidden font-sans">
      {/* Sidebar: File Tree */}
      <CollapsiblePanel
        side="left"
        defaultWidth={288}
        minWidth={240}
        maxWidth={400}
        collapsedIcon={<FolderOpen size={20} />}
        collapsedLabel="Files"
        className="border-r border-slate-800/50 glass-panel"
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
          </div>
        </div>
      </CollapsiblePanel>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full min-w-0 blueprint-grid-dark">
         {/* PDF Viewer */}
         <div className="flex-1 relative overflow-hidden">
            {selectedFile ? (
                <PdfViewer
                    file={selectedFile.file}
                    fileId={selectedFile.id}
                    pointers={pointers}
                    setPointers={setPointers}
                    selectedPointerId={selectedPointerId}
                    setSelectedPointerId={setSelectedPointerId}
                    activeTool={activeTool}
                    setActiveTool={setActiveTool}
                    onPointerCreate={handlePointerCreate}
                    isLoadingFile={isLoadingFile}
                    fileLoadError={fileLoadError}
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

      {/* Context Panel */}
      <CollapsiblePanel
        side="right"
        defaultWidth={320}
        minWidth={280}
        maxWidth={450}
        collapsedIcon={<Layers size={20} />}
        collapsedLabel="Context"
        className="border-l border-slate-800/50 glass-panel"
      >
        <div className="flex flex-col h-full">
           <div className="p-4 border-b border-white/5">
              <h2 className="font-semibold text-slate-100 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-cyan-400 shadow-glow-cyan-sm"></div>
                Context Extraction
              </h2>
           </div>
           <div ref={contextPanelRef} className="flex-1 p-4 flex flex-col items-center justify-start text-center text-slate-500 overflow-y-auto dark-scroll">
              {pointers.length === 0 ? (
                <div className="animate-fade-in">
                  <p className="text-sm text-slate-500">Draw a box on the plan to extract context.</p>
                </div>
              ) : (
                  <div className="w-full text-left space-y-3 animate-slide-up">
                    {pointers.filter(p => p.pageId === selectedFile?.id).map(pointer => (
                      <div
                        key={pointer.id}
                        data-pointer-id={pointer.id}
                        onClick={() => setSelectedPointerId(pointer.id)}
                        className={`relative p-4 rounded-xl bg-gradient-to-br from-cyan-500/10 to-blue-500/5 border transition-all cursor-pointer group ${
                          selectedPointerId === pointer.id
                            ? 'border-cyan-400 ring-1 ring-cyan-400/50'
                            : 'border-cyan-500/20 hover:border-cyan-400/40'
                        }`}
                      >
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deletePointer(pointer.id);
                          }}
                          className="absolute top-2 right-2 p-1 rounded-md text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all opacity-0 group-hover:opacity-100"
                        >
                          <X size={14} />
                        </button>
                        <input
                          type="text"
                          value={pointer.title}
                          onChange={(e) => updatePointer(pointer.id, { title: e.target.value })}
                          placeholder="Title"
                          className="w-full bg-transparent text-sm font-medium text-cyan-300 placeholder-cyan-500/50 outline-none mb-2 pr-6"
                        />
                        <textarea
                          value={pointer.description}
                          onChange={(e) => updatePointer(pointer.id, { description: e.target.value })}
                          placeholder="Description..."
                          rows={2}
                          className="w-full bg-transparent text-sm text-slate-300 placeholder-slate-500 outline-none resize-none"
                        />
                      </div>
                    ))}
                    {/* Spacer to allow last items to be centered */}
                    <div className="h-[50vh] flex-shrink-0" />
                  </div>
              )}
           </div>
        </div>
      </CollapsiblePanel>

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
