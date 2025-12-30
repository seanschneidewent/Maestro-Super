import React, { useState, useRef } from 'react';
import { FolderTree } from './FolderTree';
import { PdfViewer } from './PdfViewer';
import { ModeToggle } from '../ModeToggle';
import { AppMode, ContextPointer, ProjectFile, FileType } from '../../types';
import { Upload, Plus, BrainCircuit } from 'lucide-react';

interface SetupModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
}

export const SetupMode: React.FC<SetupModeProps> = ({ mode, setMode }) => {
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null);
  const [pointers, setPointers] = useState<ContextPointer[]>([]);
  const [activeTool, setActiveTool] = useState<'select' | 'rect' | 'pen' | 'text'>('select');
  const [uploadedFiles, setUploadedFiles] = useState<ProjectFile[]>([]);
  const folderInputRef = useRef<HTMLInputElement>(null);

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
    <div className="flex h-screen w-full bg-gradient-radial-dark text-slate-200 overflow-hidden font-sans">
      {/* Sidebar: File Tree */}
      <div className="w-72 border-r border-slate-800/50 flex flex-col glass-panel">
        <div className="p-4 border-b border-white/5 space-y-3">
            <ModeToggle mode={mode} setMode={setMode} />
            <h1 className="font-bold text-lg tracking-tight text-white">
              Maestro<span className="text-cyan-400 drop-shadow-[0_0_8px_rgba(6,182,212,0.5)]">Setup</span>
            </h1>
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

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full min-w-0 blueprint-grid-dark">
         {/* PDF Viewer */}
         <div className="flex-1 relative overflow-hidden">
            {selectedFile ? (
                <PdfViewer
                    file={selectedFile.file}
                    pointers={pointers}
                    setPointers={setPointers}
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
      <div className="w-80 border-l border-slate-800/50 glass-panel flex flex-col">
         <div className="p-4 border-b border-white/5">
            <h2 className="font-semibold text-slate-100 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-400 shadow-glow-cyan-sm"></div>
              Context Extraction
            </h2>
         </div>
         <div className="flex-1 p-4 flex flex-col items-center justify-center text-center text-slate-500 overflow-y-auto dark-scroll">
            {pointers.length === 0 ? (
              <div className="animate-fade-in">
                <p className="text-sm text-slate-500">Contextual data from pointers will appear here grouped by discipline.</p>
              </div>
            ) : (
                <div className="w-full text-left space-y-3 animate-slide-up">
                    <div className="p-4 rounded-xl bg-gradient-to-br from-cyan-500/10 to-blue-500/5 border border-cyan-500/20 hover:border-cyan-400/40 transition-all cursor-pointer group">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-cyan-400"></div>
                          <span className="text-xs text-cyan-400 font-bold uppercase tracking-wider">Electrical</span>
                        </div>
                        <div className="text-sm text-slate-300 group-hover:text-slate-200 transition-colors">Conduit routing analysis</div>
                    </div>
                    <div className="p-4 rounded-xl bg-gradient-to-br from-orange-500/10 to-amber-500/5 border border-orange-500/20 hover:border-orange-400/40 transition-all cursor-pointer group">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-orange-400"></div>
                          <span className="text-xs text-orange-400 font-bold uppercase tracking-wider">Structural</span>
                        </div>
                        <div className="text-sm text-slate-300 group-hover:text-slate-200 transition-colors">Column reinforcement details</div>
                    </div>
                </div>
            )}
         </div>
      </div>
    </div>
  );
};
