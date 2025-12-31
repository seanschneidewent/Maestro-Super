import React, { useState } from 'react';
import { AppMode, ProjectFile } from '../../types';
import { Folder, FileText, ChevronRight, ChevronLeft } from 'lucide-react';
import { AgentPanel } from './AgentPanel';
import { ModeToggle } from '../ModeToggle';

interface UseModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
}

export const UseMode: React.FC<UseModeProps> = ({ mode, setMode, projectId }) => {
  const [activePanel, setActivePanel] = useState<'specs' | 'agent' | null>('specs');
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  // Empty state - files will come from backend
  const categories: ProjectFile[] = [];

  return (
    <div className="flex h-screen w-full bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 overflow-hidden font-sans relative blueprint-grid">

      {/* LEFT PANEL: Specs / File Tree */}
      <div
        className={`absolute left-0 top-0 bottom-0 bg-white/80 backdrop-blur-xl border-r border-slate-200/50 transition-all duration-500 ease-out z-20 shadow-elevation-3 ${activePanel === 'specs' ? 'translate-x-0 w-80' : '-translate-x-full w-80'}`}
      >
        <div className="px-5 py-4 border-b border-slate-200/50 bg-white/50 space-y-3">
            <ModeToggle mode={mode} setMode={setMode} variant="light" />
            <div>
              <h1 className="font-bold text-lg text-slate-800">
                Maestro<span className="text-cyan-600">Super</span>
              </h1>
              <p className="text-xs text-slate-500">Go Time.</p>
            </div>
        </div>
        <div className="overflow-y-auto h-[calc(100%-4rem)] p-3 no-scrollbar">
            {categories.map(cat => (
                <div key={cat.id} className="mb-2">
                    <button
                        onClick={() => setExpandedCategory(expandedCategory === cat.name ? null : cat.name)}
                        className={`w-full flex items-center justify-between p-3.5 rounded-xl transition-all duration-200 ${
                          expandedCategory === cat.name
                            ? 'bg-gradient-to-r from-cyan-50 to-blue-50 shadow-sm ring-1 ring-cyan-200/50'
                            : 'hover:bg-slate-50'
                        }`}
                    >
                        <div className="flex items-center gap-3">
                            <span className={`p-2 rounded-lg transition-colors ${
                              expandedCategory === cat.name
                                ? 'bg-cyan-500 text-white shadow-glow-cyan-sm'
                                : 'bg-slate-100 text-slate-500'
                            }`}>
                              <Folder size={16} />
                            </span>
                            <span className={`font-medium transition-colors ${expandedCategory === cat.name ? 'text-cyan-700' : 'text-slate-700'}`}>
                              {cat.name}
                            </span>
                        </div>
                        <span className={`transition-transform duration-200 ${expandedCategory === cat.name ? 'rotate-90' : ''}`}>
                          <ChevronRight size={16} className="text-slate-400" />
                        </span>
                    </button>

                    {/* File List */}
                    <div className={`overflow-hidden transition-all duration-300 ease-out ${expandedCategory === cat.name ? 'max-h-96 mt-2 ml-3 space-y-1' : 'max-h-0'}`}>
                        {cat.children?.map(file => (
                            <button
                                key={file.id}
                                onClick={() => setSelectedFile(file)}
                                className={`w-full flex items-center gap-3 p-3 rounded-lg text-sm transition-all duration-150 ${
                                  selectedFile?.id === file.id
                                    ? 'bg-cyan-500 text-white shadow-glow-cyan-sm font-medium'
                                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-800'
                                }`}
                            >
                                <FileText size={14} className={selectedFile?.id === file.id ? 'text-cyan-200' : 'text-slate-400'} />
                                {file.name}
                            </button>
                        ))}
                    </div>
                </div>
            ))}
        </div>
      </div>

      {/* RIGHT PANEL: Agent Chat */}
      <div
        className={`absolute right-0 top-0 bottom-0 transition-all duration-500 ease-out z-20 ${activePanel === 'agent' ? 'translate-x-0 w-[420px]' : 'translate-x-full w-[420px]'}`}
      >
        <AgentPanel onLinkClick={(name) => console.log("Navigate to", name)} />
      </div>

      {/* CENTER: Plan Viewer */}
      <div className="flex-1 h-full relative overflow-hidden flex flex-col transition-all duration-500 ease-out"
           style={{
             marginLeft: activePanel === 'specs' ? '20rem' : '0',
             marginRight: activePanel === 'agent' ? '420px' : '0'
           }}>

           {/* Header */}
           {selectedFile && (
               <div className="absolute top-5 left-1/2 transform -translate-x-1/2 z-10 glass-light px-6 py-3 rounded-2xl flex items-center gap-4 shadow-elevation-2 animate-fade-in">
                   <div className="w-2 h-2 rounded-full bg-cyan-500 shadow-glow-cyan-sm"></div>
                   <span className="font-semibold text-slate-700">{selectedFile.name}</span>
                   <span className="w-px h-4 bg-slate-200"></span>
                   <span className="text-sm text-slate-500">Page 1 / 1</span>
               </div>
           )}

           {/* Edge Toggles */}
           {activePanel !== 'specs' && (
                <button
                    onClick={() => setActivePanel('specs')}
                    className="absolute left-0 top-1/2 -translate-y-1/2 z-30 bg-white/90 backdrop-blur-sm border border-l-0 border-slate-200/50 shadow-elevation-2 rounded-r-2xl py-10 px-2 hover:bg-cyan-50 hover:border-cyan-200 group transition-all duration-200"
                >
                    <span className="writing-vertical text-xs font-bold text-slate-400 group-hover:text-cyan-600 uppercase tracking-widest flex items-center gap-2">
                        <Folder size={14} className="rotate-90" /> Plans
                    </span>
                </button>
           )}

           {activePanel !== 'agent' && (
                <button
                    onClick={() => setActivePanel('agent')}
                    className="absolute right-0 top-1/2 -translate-y-1/2 z-30 bg-gradient-to-l from-cyan-500 to-cyan-600 text-white shadow-glow-cyan rounded-l-2xl py-10 px-2 hover:from-cyan-400 hover:to-cyan-500 group transition-all duration-200"
                >
                    <span className="writing-vertical text-xs font-bold uppercase tracking-widest flex items-center gap-2">
                        <ChevronLeft size={14} /> AI Agent
                    </span>
                </button>
           )}

           {/* Viewer Content */}
           <div className="flex-1 flex items-center justify-center p-8 overflow-auto">
                <div className="text-center animate-fade-in">
                    <div className="p-8 rounded-2xl bg-white/50 backdrop-blur-sm border border-slate-200/50 shadow-elevation-1">
                      <Folder size={48} className="mx-auto mb-4 text-slate-300" />
                      <p className="text-slate-500">No plans uploaded yet</p>
                    </div>
                </div>
           </div>

      </div>

    </div>
  );
};
