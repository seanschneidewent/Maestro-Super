export interface OcrSpan {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
}

export interface PointerReference {
  id: string;
  targetPageId: string;
  targetPageName: string;
  justification: string;
}

export interface ContextPointer {
  id: string;
  pageId: string;
  title: string;
  description: string;
  textSpans?: string[];
  ocrData?: OcrSpan[];  // Word-level OCR with positions for highlighting
  bboxX: number;
  bboxY: number;
  bboxWidth: number;
  bboxHeight: number;
  pngPath?: string;
  hasEmbedding?: boolean;
  references?: PointerReference[];
  isGenerating?: boolean;  // True while waiting for AI analysis
}
