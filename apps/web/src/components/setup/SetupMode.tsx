import React, { useState, useRef, useEffect } from 'react';
import { FolderTree } from './FolderTree';
import { PdfViewer } from './PdfViewer';
import { ModeToggle } from '../ModeToggle';
import { CollapsiblePanel } from '../ui/CollapsiblePanel';
import { AppMode, ContextPointer, ProjectFile, FileType } from '../../types';
import { Upload, Plus, BrainCircuit, FolderOpen, Layers, X } from 'lucide-react';

interface SetupModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
}

export const SetupMode: React.FC<SetupModeProps> = ({ mode, setMode }) => {
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null);
  const [pointers, setPointers] = useState<ContextPointer[]>([]);
  const [selectedPointerId, setSelectedPointerId] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<'select' | 'rect' | 'text'>('select');
  const [uploadedFiles, setUploadedFiles] = useState<ProjectFile[]>([]);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const contextPanelRef = useRef<HTMLDivElement>(null);

  const updatePointer = (id: string, updates: Partial<ContextPointer>) => {
    setPointers(prev => prev.map(p => p.id === id ? { ...p, ...updates } : p));
  };

  const deletePointer = (id: string) => {
    setPointers(prev => prev.filter(p => p.id !== id));
    if (selectedPointerId === id) {
      setSelectedPointerId(null);
    }
  };

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

  const getFileType = (filename: string): FileType => {
    const ext = filename.toLowerCase().split('.').pop();
    switch (ext) {
      case 'pdf': return FileType.PDF;
      case 'csv': return FileType.CSV;
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
      case 'webp': return FileType.IMAGE;
      default: return FileType.PDF;
    }
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

  const handleFolderUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Sort files by path first to ensure consistent processing order
    const sortedFiles = Array.from(files).sort((a, b) =>
      a.webkitRelativePath.localeCompare(b.webkitRelativePath, undefined, { numeric: true, sensitivity: 'base' })
    );

    // Build folder structure from file paths
    const fileMap = new Map<string, ProjectFile>();
    const rootFiles: ProjectFile[] = [];

    sortedFiles.forEach(file => {
      const pathParts = file.webkitRelativePath.split('/');
      let currentPath = '';

      pathParts.forEach((part, index) => {
        const isLast = index === pathParts.length - 1;
        const parentPath = currentPath;
        currentPath = currentPath ? `${currentPath}/${part}` : part;

        if (!fileMap.has(currentPath)) {
          const newFile: ProjectFile = {
            id: crypto.randomUUID(),
            name: part,
            type: isLast ? getFileType(part) : FileType.FOLDER,
            children: isLast ? undefined : [],
            parentId: parentPath ? fileMap.get(parentPath)?.id : undefined,
            file: isLast ? file : undefined, // Store the actual File object
          };

          fileMap.set(currentPath, newFile);

          if (parentPath && fileMap.has(parentPath)) {
            const parent = fileMap.get(parentPath)!;
            parent.children = parent.children || [];
            parent.children.push(newFile);
          } else if (index === 0) {
            rootFiles.push(newFile);
          }
        }
      });
    });

    // Sort the final tree: folders first, then files, alphabetically
    setUploadedFiles(sortFiles(rootFiles));
    // Reset input so the same folder can be selected again
    e.target.value = '';
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

          <div className="p-3 flex gap-2 border-b border-white/5">
               <button className="flex-1 btn-primary text-white text-xs py-2.5 rounded-lg flex justify-center items-center gap-1.5 font-medium">
                  <Plus size={14} /> New Folder
               </button>
               <button className="flex-1 bg-slate-700/50 hover:bg-slate-600/50 text-white text-xs py-2.5 rounded-lg flex justify-center items-center gap-1.5 font-medium transition-all border border-slate-600/30">
                  <Upload size={14} /> Add Files
               </button>
          </div>

          <FolderTree
            files={uploadedFiles}
            onFileSelect={setSelectedFile}
            selectedFileId={selectedFile?.id || null}
          />

          {/* Upload Prompts */}
          <div className="p-4 border-t border-white/5">
              <input
                ref={folderInputRef}
                type="file"
                className="hidden"
                onChange={handleFolderUpload}
                {...{ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>}
              />
              <button
                onClick={() => folderInputRef.current?.click()}
                className="w-full py-3.5 rounded-lg bg-gradient-to-r from-cyan-600/20 to-blue-600/20 border border-cyan-500/30 text-cyan-200 text-sm font-medium hover:border-cyan-400/50 hover:from-cyan-600/30 hover:to-blue-600/30 transition-all shadow-lg shadow-cyan-900/10 group"
              >
                  <span className="group-hover:drop-shadow-[0_0_8px_rgba(6,182,212,0.5)] transition-all">+ Upload Plans</span>
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
                    {pointers.filter(p => p.fileId === selectedFile?.id).map(pointer => (
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
    </div>
  );
};
