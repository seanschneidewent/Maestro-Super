// Field Mode Types
export type FieldViewMode = 'standard' | 'response'

// OCR word with bounding box for text highlighting
export interface OcrWord {
  id: number
  text: string
  bbox: {
    x0: number      // Pixel coordinates
    y0: number
    x1: number
    y1: number
    width: number
    height: number
  }
  role?: string        // e.g., "dimension", "detail_title", "material_spec"
  region_type?: string // e.g., "detail", "notes", "schedule"
}

// Legacy pointer type (being phased out)
export interface FieldPointer {
  id: string
  label: string
  region: {
    bboxX: number      // 0-1 normalized
    bboxY: number      // 0-1 normalized
    bboxWidth: number  // 0-1 normalized
    bboxHeight: number // 0-1 normalized
  }
  answer: string
  evidence: {
    type: 'quote' | 'explanation'
    text: string
  }
}

export interface FieldPage {
  id: string
  pageNumber: number
  title: string
  pngDataUrl: string
  intro: string
  pointers: FieldPointer[]     // Legacy - being phased out
  highlights?: OcrWord[]       // New - text highlighting from agent
  imageWidth?: number          // For normalizing OCR coordinates
  imageHeight?: number
}

export interface FieldResponse {
  id: string
  query: string
  summary: string
  displayTitle: string | null
  pages: FieldPage[]
}
