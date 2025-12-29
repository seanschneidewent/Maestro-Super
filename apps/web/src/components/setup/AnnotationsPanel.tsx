import React from 'react';
import { ContextPointer } from '../../types';
import { Crosshair, Loader2, AlertCircle, X, CheckCircle2 } from 'lucide-react';

interface AnnotationsPanelProps {
  pointers: ContextPointer[];
  onDelete: (id: string) => void;
}

export const AnnotationsPanel: React.FC<AnnotationsPanelProps> = ({ pointers, onDelete }) => {
  return (
    <div className="h-56 glass-panel border-t border-white/5 flex flex-col">
      <div className="px-4 py-3 border-b border-white/5 flex justify-between items-center">
        <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Crosshair size={16} className="text-cyan-400" />
          Annotations
          {pointers.length > 0 && (
            <span className="ml-1 px-2 py-0.5 bg-cyan-500/20 text-cyan-400 text-xs rounded-full font-medium">
              {pointers.length}
            </span>
          )}
        </h3>
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-hidden p-4 flex gap-4 dark-scroll">
        {pointers.length === 0 ? (
          <div className="w-full flex flex-col items-center justify-center border border-dashed border-slate-700/50 rounded-xl text-slate-500 bg-slate-800/20">
            <Crosshair size={28} className="mb-2 text-slate-600" />
            <p className="text-sm text-slate-500">No annotations yet. Draw rectangles on the plan.</p>
          </div>
        ) : (
          pointers.map((pointer, index) => (
            <div
              key={pointer.id}
              className="min-w-[280px] w-[280px] glass rounded-xl p-4 flex flex-col relative group hover:border-cyan-500/30 transition-all animate-slide-up"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <button
                onClick={() => onDelete(pointer.id)}
                className="absolute top-3 right-3 p-1 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all"
              >
                <X size={14} />
              </button>

              <div className="flex items-center gap-2.5 mb-3">
                {pointer.status === 'generating' ? (
                  <div className="p-1.5 rounded-lg bg-cyan-500/20">
                    <Loader2 size={14} className="text-cyan-400 animate-spin" />
                  </div>
                ) : pointer.status === 'error' ? (
                  <div className="p-1.5 rounded-lg bg-red-500/20">
                    <AlertCircle size={14} className="text-red-400" />
                  </div>
                ) : (
                  <div className="p-1.5 rounded-lg bg-emerald-500/20">
                    <CheckCircle2 size={14} className="text-emerald-400" />
                  </div>
                )}
                <span className="font-medium text-slate-200 text-sm truncate pr-6">{pointer.title}</span>
              </div>

              <div className="flex-1 bg-slate-900/30 rounded-lg p-3 mb-3 overflow-y-auto border border-white/5">
                 <p className="text-xs text-slate-400 whitespace-pre-wrap leading-relaxed">
                    {pointer.status === 'generating' ? (
                      <span className="flex items-center gap-2">
                        <span className="inline-block w-1 h-1 bg-cyan-400 rounded-full animate-pulse"></span>
                        AI Analysis in progress...
                      </span>
                    ) : pointer.description}
                 </p>
              </div>

              <div className="flex justify-between items-center mt-auto">
                <span className="text-[10px] bg-slate-700/50 text-slate-400 px-2.5 py-1 rounded-full border border-slate-600/30">
                    Page {pointer.pageNumber}
                </span>
                {pointer.status === 'error' && (
                    <button className="text-[10px] text-cyan-400 hover:text-cyan-300 font-medium transition-colors">Retry</button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
