import React, { useState, useEffect, useMemo } from 'react';
import { ProjectFile, FileType } from '../../types';
import { ChevronRight, ChevronDown, Folder, FileText, Image, Box, File, Check } from 'lucide-react';

// Helper to find path to a file (returns array of parent IDs)
const findPathToFile = (files: ProjectFile[], targetId: string, path: string[] = []): string[] | null => {
  for (const file of files) {
    if (file.id === targetId) {
      return path;
    }
    if (file.children) {
      const result = findPathToFile(file.children, targetId, [...path, file.id]);
      if (result) return result;
    }
  }
  return null;
};

interface FileNodeProps {
  node: ProjectFile;
  level: number;
  onSelect: (file: ProjectFile) => void;
  selectedId: string | null;
  expandedIds?: Set<string>;
  isDeleteMode?: boolean;
  selectedForDeletion?: Set<string>;
  onToggleSelection?: (fileId: string) => void;
}

const FileNode: React.FC<FileNodeProps> = ({
  node,
  level,
  onSelect,
  selectedId,
  expandedIds,
  isDeleteMode,
  selectedForDeletion,
  onToggleSelection,
}) => {
  // Initialize open state based on whether this folder should be expanded
  const shouldBeExpanded = expandedIds?.has(node.id) ?? false;
  const [isOpen, setIsOpen] = useState(shouldBeExpanded);

  // Update open state when expandedIds changes (e.g., on mount with saved selection)
  useEffect(() => {
    if (shouldBeExpanded && !isOpen) {
      setIsOpen(true);
    }
  }, [shouldBeExpanded]);
  const isFolder = node.type === FileType.FOLDER;
  const isSelected = selectedId === node.id;
  const isMarkedForDeletion = selectedForDeletion?.has(node.id) ?? false;

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isDeleteMode && onToggleSelection) {
      onToggleSelection(node.id);
    } else if (isFolder) {
      setIsOpen(!isOpen);
    } else {
      onSelect(node);
    }
  };

  const handleChevronClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isFolder) setIsOpen(!isOpen);
  };

  const getIcon = () => {
    if (isFolder) return <Folder size={16} className={isOpen ? "text-cyan-400" : "text-slate-400"} />;
    if (node.type === FileType.PDF) return <FileText size={16} className="text-rose-400" />;
    if (node.type === FileType.IMAGE) return <Image size={16} className="text-violet-400" />;
    if (node.type === FileType.MODEL) return <Box size={16} className="text-orange-400" />;
    return <File size={16} className="text-slate-500" />;
  };

  const getRowStyles = () => {
    if (isMarkedForDeletion) {
      return 'bg-red-500/20 border-l-2 border-red-500 text-red-300';
    }
    if (isSelected && !isDeleteMode) {
      return 'bg-cyan-500/15 border-l-2 border-cyan-400 text-cyan-300';
    }
    return 'border-l-2 border-transparent hover:bg-white/5';
  };

  return (
    <div className="select-none">
      <div
        className={`flex items-center py-2 px-2 mx-2 my-0.5 cursor-pointer rounded-lg transition-all duration-150 ${getRowStyles()}`}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
        onClick={handleToggle}
      >
        {isDeleteMode && (
          <span
            className={`mr-2 w-4 h-4 rounded border flex items-center justify-center transition-all ${
              isMarkedForDeletion
                ? 'bg-red-500 border-red-500'
                : 'border-slate-500 hover:border-red-400'
            }`}
          >
            {isMarkedForDeletion && <Check size={12} className="text-white" />}
          </span>
        )}
        <span
          className={`mr-1.5 transition-transform duration-200 ${isFolder && isOpen ? 'text-cyan-400' : 'text-slate-500'}`}
          onClick={handleChevronClick}
        >
          {isFolder && (
            <span className={`inline-block transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}>
              <ChevronRight size={14} />
            </span>
          )}
          {!isFolder && <div className="w-[14px]" />}
        </span>
        <span className="mr-2.5">{getIcon()}</span>
        <span className={`text-sm transition-colors ${
          isMarkedForDeletion
            ? 'text-red-300 font-medium'
            : isSelected && !isDeleteMode
              ? 'text-cyan-300 font-medium'
              : 'text-slate-300 hover:text-slate-200'
        }`}>{node.name}</span>
      </div>
      {isFolder && isOpen && node.children && (
        <div className="animate-fade-in">
          {node.children.map(child => (
            <FileNode
              key={child.id}
              node={child}
              level={level + 1}
              onSelect={onSelect}
              selectedId={selectedId}
              expandedIds={expandedIds}
              isDeleteMode={isDeleteMode}
              selectedForDeletion={selectedForDeletion}
              onToggleSelection={onToggleSelection}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface FolderTreeProps {
  files: ProjectFile[];
  onFileSelect: (file: ProjectFile) => void;
  selectedFileId: string | null;
  expandToFileId?: string | null;
  isDeleteMode?: boolean;
  selectedForDeletion?: Set<string>;
  onToggleSelection?: (fileId: string) => void;
}

export const FolderTree: React.FC<FolderTreeProps> = ({
  files,
  onFileSelect,
  selectedFileId,
  expandToFileId,
  isDeleteMode,
  selectedForDeletion,
  onToggleSelection,
}) => {
  // Calculate which folders should be expanded to reveal the selected file
  const expandedIds = useMemo(() => {
    if (!expandToFileId) return new Set<string>();
    const path = findPathToFile(files, expandToFileId);
    return new Set(path || []);
  }, [files, expandToFileId]);

  return (
    <div className="flex-1 overflow-y-auto dark-scroll">
      {files.map(node => (
        <FileNode
          key={node.id}
          node={node}
          level={0}
          onSelect={onFileSelect}
          selectedId={selectedFileId}
          expandedIds={expandedIds}
          isDeleteMode={isDeleteMode}
          selectedForDeletion={selectedForDeletion}
          onToggleSelection={onToggleSelection}
        />
      ))}
    </div>
  );
};
