import { useState, useRef, useCallback } from 'react'
import { Mic, Loader2, Send } from 'lucide-react'

interface QueryInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  onRecordingComplete: (audioBlob: Blob) => void
  isProcessing: boolean
  placeholder?: string
}

export function QueryInput({
  value,
  onChange,
  onSubmit,
  onRecordingComplete,
  isProcessing,
  placeholder = 'Ask about your plans...',
}: QueryInputProps) {
  const [isRecording, setIsRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const hasText = value.trim().length > 0

  const startRecording = useCallback(async () => {
    if (isProcessing) return

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Try webm first, fall back to other formats
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4')
        ? 'audio/mp4'
        : 'audio/ogg'

      const mediaRecorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
        }
      }

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType })
        onRecordingComplete(blob)
        chunksRef.current = []

        // Clean up stream
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop())
          streamRef.current = null
        }
      }

      mediaRecorder.start()
      setIsRecording(true)
    } catch (error) {
      console.error('Failed to start recording:', error)
    }
  }, [isProcessing, onRecordingComplete])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }, [])

  const handlePointerDown = () => {
    if (!hasText) {
      startRecording()
    }
  }

  const handlePointerUp = () => {
    if (isRecording) {
      stopRecording()
    }
  }

  const handlePointerLeave = () => {
    if (isRecording) {
      stopRecording()
    }
  }

  const handleButtonClick = () => {
    if (hasText && !isProcessing) {
      onSubmit()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && hasText && !isProcessing) {
      e.preventDefault()
      onSubmit()
    }
  }

  // Button size matches the pill height for seamless integration
  const buttonSize = 44

  return (
    <div
      className={`
        flex items-center
        bg-white/90 backdrop-blur-md
        border border-slate-200/50
        rounded-full
        shadow-lg
        transition-all duration-150
        ${isRecording ? 'ring-2 ring-red-500' : ''}
      `}
      style={{ paddingLeft: 16, paddingRight: 4, paddingTop: 4, paddingBottom: 4 }}
    >
      {/* Text input */}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={isProcessing || isRecording}
        className="flex-1 bg-transparent text-slate-800 placeholder:text-slate-400 outline-none text-sm min-w-0"
      />

      {/* Mic/Send button - circular, inside the pill */}
      <button
        type="button"
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerLeave}
        onClick={handleButtonClick}
        disabled={isProcessing}
        className={`
          flex-shrink-0 rounded-full
          flex items-center justify-center
          transition-all duration-150
          ${
            isProcessing
              ? 'bg-slate-200 cursor-not-allowed'
              : isRecording
              ? 'bg-red-500/20 scale-105'
              : hasText
              ? 'bg-cyan-500 hover:bg-cyan-600'
              : 'bg-slate-100 hover:bg-slate-200'
          }
        `}
        style={{ width: buttonSize, height: buttonSize }}
      >
        {isProcessing ? (
          <Loader2 size={20} className="text-slate-400 animate-spin" />
        ) : isRecording ? (
          <Mic size={20} className="text-red-500" />
        ) : hasText ? (
          <Send size={18} className="text-white" />
        ) : (
          <Mic size={20} className="text-slate-500" />
        )}
      </button>
    </div>
  )
}

// Keep the old export for backwards compatibility during transition
export const HoldToTalk = QueryInput
