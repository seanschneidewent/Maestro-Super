import React, { useState } from 'react';
import { ProjectFile, FileType } from '../../types';
import { ChevronRight, ChevronDown, Folder, FileText, Image, Box, File } from 'lucide-react';

interface FileNodeProps {
  node: ProjectFile;
  level: number;
  onSelect: (file: ProjectFile) => void;
  selectedId: string | null;
}

const FileNode: React.FC<FileNodeProps> = ({ node, level, onSelect, selectedId }) => {
  const [isOpen, setIsOpen] = useState(false);
  const isFolder = node.type === FileType.FOLDER;
  const isSelected = selectedId === node.id;

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isFolder) setIsOpen(!isOpen);
    else onSelect(node);
  };

  const getIcon = () => {
    if (isFolder) return <Folder size={16} className={isOpen ? "text-cyan-400" : "text-slate-400"} />;
    if (node.type === FileType.PDF) return <FileText size={16} className="text-rose-400" />;
    if (node.type === FileType.IMAGE) return <Image size={16} className="text-violet-400" />;
    if (node.type === FileType.MODEL) return <Box size={16} className="text-orange-400" />;
    return <File size={16} className="text-slate-500" />;
  };

  return (
    <div className="select-none">
      <div
        className={`flex items-center py-2 px-2 mx-2 my-0.5 cursor-pointer rounded-lg transition-all duration-150 ${
          isSelected
            ? 'bg-cyan-500/15 border-l-2 border-cyan-400 text-cyan-300'
            : 'border-l-2 border-transparent hover:bg-white/5'
        }`}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
        onClick={handleToggle}
      >
        <span className={`mr-1.5 transition-transform duration-200 ${isFolder && isOpen ? 'text-cyan-400' : 'text-slate-500'}`}>
          {isFolder && (
            <span className={`inline-block transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}>
              <ChevronRight size={14} />
            </span>
          )}
          {!isFolder && <div className="w-[14px]" />}
        </span>
        <span className="mr-2.5">{getIcon()}</span>
        <span className={`text-sm transition-colors ${isSelected ? 'text-cyan-300 font-medium' : 'text-slate-300 hover:text-slate-200'}`}>{node.name}</span>
      </div>
      {isFolder && isOpen && node.children && (
        <div className="animate-fade-in">
          {node.children.map(child => (
            <FileNode key={child.id} node={child} level={level + 1} onSelect={onSelect} selectedId={selectedId} />
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
}

export const FolderTree: React.FC<FolderTreeProps> = ({ files, onFileSelect, selectedFileId }) => {
  return (
    <div className="flex-1 overflow-y-auto dark-scroll">
      {files.map(node => (
        <FileNode key={node.id} node={node} level={0} onSelect={onFileSelect} selectedId={selectedFileId} />
      ))}
    </div>
  );
};
