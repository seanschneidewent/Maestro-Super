import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ZoomIn, ZoomOut, Maximize, MousePointer2, Pen, Square, Type } from 'lucide-react';
import { ContextPointer } from '../../types';
import { SAMPLE_IMAGE_URL } from '../../constants';
import { GeminiService } from '../../services/geminiService';

interface PdfViewerProps {
  fileId: string;
  pointers: ContextPointer[];
  setPointers: React.Dispatch<React.SetStateAction<ContextPointer[]>>;
  activeTool: 'select' | 'rect' | 'pen' | 'text';
  setActiveTool: (tool: 'select' | 'rect' | 'pen' | 'text') => void;
}

export const PdfViewer: React.FC<PdfViewerProps> = ({ fileId, pointers, setPointers, activeTool, setActiveTool }) => {
  const [scale, setScale] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [tempRect, setTempRect] = useState<{ x: number, y: number, w: number, h: number } | null>(null);

  // Reset zoom on file change
  useEffect(() => {
    setScale(1);
  }, [fileId]);

  const handleZoom = (delta: number) => {
    setScale(prev => Math.min(Math.max(prev + delta, 0.5), 3));
  };

  const getNormalizedCoords = (e: React.MouseEvent) => {
    if (!imageRef.current) return { x: 0, y: 0 };
    const rect = imageRef.current.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) / rect.width,
      y: (e.clientY - rect.top) / rect.height
    };
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (activeTool !== 'rect') return;
    const coords = getNormalizedCoords(e);
    setStartPos(coords);
    setIsDrawing(true);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDrawing || activeTool !== 'rect') return;
    const coords = getNormalizedCoords(e);
    
    setTempRect({
      x: Math.min(startPos.x, coords.x),
      y: Math.min(startPos.y, coords.y),
      w: Math.abs(coords.x - startPos.x),
      h: Math.abs(coords.y - startPos.y)
    });
  };

  const handleMouseUp = async () => {
    if (!isDrawing || !tempRect) {
      setIsDrawing(false);
      return;
    }

    const newPointer: ContextPointer = {
      id: crypto.randomUUID(),
      pageNumber: 1,
      bounds: {
        xNorm: tempRect.x,
        yNorm: tempRect.y,
        wNorm: tempRect.w,
        hNorm: tempRect.h
      },
      title: "New Annotation",
      description: "Analyzing region...",
      status: 'generating'
    };

    setPointers(prev => [...prev, newPointer]);
    setIsDrawing(false);
    setTempRect(null);
    setActiveTool('select');

    // Simulate Image Capture & AI Analysis
    try {
        const analysis = await GeminiService.analyzePointer("dummy_base64", "Construction plan detail");
        setPointers(prev => prev.map(p => 
            p.id === newPointer.id 
            ? { ...p, status: 'complete', description: analysis, title: "Detail Analysis" } 
            : p
        ));
    } catch (e) {
        setPointers(prev => prev.map(p => p.id === newPointer.id ? { ...p, status: 'error' } : p));
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full relative overflow-hidden">
      {/* Toolbar - Glassmorphism */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1 glass rounded-xl p-1.5 toolbar-float animate-fade-in">
        <div className="flex flex-col gap-1 border-b border-white/10 pb-2 mb-1">
          <button
            onClick={() => handleZoom(0.2)}
            className="p-2.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all" title="Zoom In">
            <ZoomIn size={18} />
          </button>
          <button
            onClick={() => handleZoom(-0.2)}
            className="p-2.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all" title="Zoom Out">
            <ZoomOut size={18} />
          </button>
          <button
            onClick={() => setScale(1)}
            className="p-2.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all" title="Reset Zoom">
            <Maximize size={18} />
          </button>
        </div>
        <div className="flex flex-col gap-1">
           <button
             onClick={() => setActiveTool('select')}
             className={`p-2.5 rounded-lg transition-all ${activeTool === 'select' ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}>
             <MousePointer2 size={18} />
           </button>
           <button
             onClick={() => setActiveTool('rect')}
             className={`p-2.5 rounded-lg transition-all ${activeTool === 'rect' ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}>
             <Square size={18} />
           </button>
           <button
             onClick={() => setActiveTool('pen')}
             className={`p-2.5 rounded-lg transition-all ${activeTool === 'pen' ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}>
             <Pen size={18} />
           </button>
        </div>
      </div>

      {/* Canvas Area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto flex items-center justify-center p-8 bg-gradient-radial-dark cursor-crosshair"
      >
        <div 
            className="relative shadow-2xl transition-transform duration-200 ease-out origin-center"
            style={{ 
                width: '800px', // Base width
                transform: `scale(${scale})` 
            }}
        >
          {/* Mock PDF Image */}
          <img 
            ref={imageRef}
            src={SAMPLE_IMAGE_URL} 
            alt="Plan" 
            className="w-full h-auto select-none pointer-events-auto bg-white"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onDragStart={(e) => e.preventDefault()}
          />

          {/* Render Existing Pointers */}
          {pointers.map(p => (
            <div
              key={p.id}
              className={`absolute pointer-box cursor-pointer group animate-scale-in ${p.status === 'generating' ? 'generating' : ''}`}
              style={{
                left: `${p.bounds.xNorm * 100}%`,
                top: `${p.bounds.yNorm * 100}%`,
                width: `${p.bounds.wNorm * 100}%`,
                height: `${p.bounds.hNorm * 100}%`,
              }}
            >
                <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 glass px-3 py-1.5 rounded-lg whitespace-nowrap z-10 pointer-events-none transition-opacity duration-200">
                    <span className="text-xs text-white font-medium">{p.title}</span>
                    {p.status === 'generating' && (
                      <span className="ml-2 inline-block w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse"></span>
                    )}
                </div>
            </div>
          ))}

          {/* Render Temp Rect */}
          {tempRect && (
            <div
              className="absolute border-2 border-cyan-400 bg-cyan-400/15 rounded-sm shadow-glow-cyan animate-pulse"
              style={{
                left: `${tempRect.x * 100}%`,
                top: `${tempRect.y * 100}%`,
                width: `${tempRect.w * 100}%`,
                height: `${tempRect.h * 100}%`,
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
};
