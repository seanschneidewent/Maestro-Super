import {
  forwardRef,
  useImperativeHandle,
  useRef,
  useState,
  useCallback,
} from 'react'
import {
  TransformWrapper,
  TransformComponent,
  ReactZoomPanPinchRef,
} from 'react-zoom-pan-pinch'
import { FieldPointer, OcrWord } from '../../types'
import { PointerOverlay } from './PointerOverlay'
import { TextHighlightOverlay } from './TextHighlightOverlay'

interface PageViewerProps {
  pngDataUrl: string | null
  pointers: FieldPointer[]
  activePointerId: string | null
  onPointerTap: (pointer: FieldPointer) => void
  // New: text highlighting from agent
  highlights?: OcrWord[]
  originalImageWidth?: number   // Original image width from OCR
  originalImageHeight?: number  // Original image height from OCR
}

export interface PageViewerHandle {
  zoomToPointer: (pointer: FieldPointer) => void
}

export const PageViewer = forwardRef<PageViewerHandle, PageViewerProps>(
  function PageViewer({
    pngDataUrl,
    pointers,
    activePointerId,
    onPointerTap,
    highlights,
    originalImageWidth,
    originalImageHeight,
  }, ref) {
    const transformRef = useRef<ReactZoomPanPinchRef>(null)
    const imageRef = useRef<HTMLImageElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 })

    const handleImageLoad = useCallback(() => {
      if (imageRef.current) {
        setImageDimensions({
          width: imageRef.current.naturalWidth,
          height: imageRef.current.naturalHeight,
        })
      }
    }, [])

    useImperativeHandle(ref, () => ({
      zoomToPointer: (pointer: FieldPointer) => {
        if (!transformRef.current || !imageRef.current || !containerRef.current) return

        const { bboxX, bboxY, bboxWidth, bboxHeight } = pointer.region
        const imgWidth = imageRef.current.clientWidth
        const imgHeight = imageRef.current.clientHeight
        const containerWidth = containerRef.current.clientWidth
        const containerHeight = containerRef.current.clientHeight

        // Calculate pointer center in pixels (relative to image)
        const centerX = (bboxX + bboxWidth / 2) * imgWidth
        const centerY = (bboxY + bboxHeight / 2) * imgHeight

        const scale = 2.5

        // Calculate position to center the pointer in viewport
        const posX = containerWidth / 2 - centerX * scale
        const posY = containerHeight / 2 - centerY * scale

        transformRef.current.setTransform(posX, posY, scale, 300, 'easeOut')
      },
    }))

    if (!pngDataUrl) {
      return (
        <div className="relative flex-1 overflow-hidden bg-slate-950 flex items-center justify-center">
          <p className="text-slate-500 text-lg">Select a page to view</p>
        </div>
      )
    }

    return (
      <div ref={containerRef} className="relative flex-1 overflow-hidden bg-slate-950">
        <TransformWrapper
          ref={transformRef}
          initialScale={1}
          minScale={0.5}
          maxScale={5}
          centerOnInit={true}
          doubleClick={{ mode: 'reset' }}
        >
          <TransformComponent
            wrapperClass="!w-full !h-full"
            contentClass="!w-full !h-full flex items-center justify-center"
          >
            <div className="relative">
              <img
                ref={imageRef}
                src={pngDataUrl}
                alt="Plan page"
                onLoad={handleImageLoad}
                className="max-w-full max-h-full object-contain"
                draggable={false}
              />
              {/* Text highlights from agent */}
              {imageDimensions.width > 0 && highlights && highlights.length > 0 && (
                <TextHighlightOverlay
                  highlights={highlights}
                  imageWidth={imageRef.current?.clientWidth || imageDimensions.width}
                  imageHeight={imageRef.current?.clientHeight || imageDimensions.height}
                  originalWidth={originalImageWidth}
                  originalHeight={originalImageHeight}
                />
              )}
              {/* Legacy pointer overlays */}
              {imageDimensions.width > 0 &&
                pointers.map((pointer) => (
                  <PointerOverlay
                    key={pointer.id}
                    pointer={pointer}
                    isActive={pointer.id === activePointerId}
                    imageWidth={imageRef.current?.clientWidth || imageDimensions.width}
                    imageHeight={imageRef.current?.clientHeight || imageDimensions.height}
                    onTap={() => onPointerTap(pointer)}
                  />
                ))}
            </div>
          </TransformComponent>
        </TransformWrapper>
      </div>
    )
  }
)
