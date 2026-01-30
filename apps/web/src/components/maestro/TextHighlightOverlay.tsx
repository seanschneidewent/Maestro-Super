import { OcrWord } from '../../types'

interface TextHighlightOverlayProps {
  highlights: OcrWord[]
  imageWidth: number       // Actual rendered image width in pixels
  imageHeight: number      // Actual rendered image height in pixels
  originalWidth?: number   // Original image width from OCR (for coordinate conversion)
  originalHeight?: number  // Original image height from OCR
}

/**
 * Renders SVG rectangles over text that should be highlighted.
 *
 * OCR coordinates are in pixels relative to the original image size.
 * We convert them to percentages for responsive positioning.
 */
export function TextHighlightOverlay({
  highlights,
  imageWidth,
  imageHeight,
  originalWidth,
  originalHeight,
}: TextHighlightOverlayProps) {
  if (!highlights || highlights.length === 0) return null
  if (imageWidth === 0 || imageHeight === 0) return null

  // Use original dimensions if provided, otherwise assume 1:1 with rendered size
  const sourceWidth = originalWidth || imageWidth
  const sourceHeight = originalHeight || imageHeight

  return (
    <svg
      className="absolute inset-0 pointer-events-none"
      style={{ width: imageWidth, height: imageHeight }}
      viewBox={`0 0 ${sourceWidth} ${sourceHeight}`}
      preserveAspectRatio="none"
    >
      {highlights.map((word, idx) => {
        if (!word.bbox) return null

        const { x0, y0, width, height } = word.bbox

        // Determine color based on source/role
        const fillColor = getHighlightColor(word)

        return (
          <g key={word.id ?? idx}>
            {/* Highlight rectangle */}
            <rect
              x={x0}
              y={y0}
              width={width}
              height={height}
              fill={fillColor}
              fillOpacity={0.3}
              stroke={fillColor}
              strokeWidth={2}
              strokeOpacity={0.8}
              rx={2}
            />
          </g>
        )
      })}
    </svg>
  )
}

/**
 * Get highlight color based on semantic role.
 */
function getHighlightColor(word: OcrWord): string {
  if (word.source === 'agent' || word.confidence === 'verified_via_zoom') {
    return '#22c55e' // green-500 (agent-verified)
  }
  if (word.source === 'search') {
    return '#facc15' // yellow-400 (search-matched)
  }
  return getRoleColor(word.role)
}

function getRoleColor(role?: string): string {
  switch (role) {
    case 'dimension':
      return '#3b82f6' // blue-500
    case 'detail_title':
      return '#8b5cf6' // violet-500
    case 'material_spec':
      return '#10b981' // emerald-500
    case 'reference':
      return '#f59e0b' // amber-500
    case 'note_text':
    case 'note_number':
      return '#6366f1' // indigo-500
    case 'schedule_title':
    case 'column_header':
    case 'cell_value':
      return '#ec4899' // pink-500
    case 'label':
    case 'callout':
      return '#14b8a6' // teal-500
    default:
      return '#f97316' // orange-500 (default highlight color)
  }
}
