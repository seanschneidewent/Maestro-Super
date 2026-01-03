import { useState, useRef, useCallback } from 'react'
import { Mic, Loader2 } from 'lucide-react'

interface HoldToTalkProps {
  onRecordingComplete: (audioBlob: Blob) => void
  isProcessing: boolean
}

export function HoldToTalk({ onRecordingComplete, isProcessing }: HoldToTalkProps) {
  const [isRecording, setIsRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)

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
    startRecording()
  }

  const handlePointerUp = () => {
    stopRecording()
  }

  const handlePointerLeave = () => {
    if (isRecording) {
      stopRecording()
    }
  }

  return (
    <button
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerLeave}
      disabled={isProcessing}
      className={`
        fixed bottom-6 right-6 z-30
        w-16 h-16 rounded-full
        flex items-center justify-center
        transition-all duration-150
        ${
          isProcessing
            ? 'bg-slate-800/80 backdrop-blur-sm border border-slate-700/50 opacity-50 cursor-not-allowed'
            : isRecording
            ? 'bg-red-500/20 backdrop-blur-sm border border-slate-700/50 ring-2 ring-red-500 scale-105'
            : 'bg-slate-800/80 backdrop-blur-sm border border-slate-700/50 hover:bg-slate-700/80'
        }
      `}
    >
      {isProcessing ? (
        <Loader2 size={24} className="text-slate-400 animate-spin" />
      ) : isRecording ? (
        <Mic size={24} className="text-red-500" />
      ) : (
        <Mic size={24} className="text-blue-400 animate-pulse" />
      )}
    </button>
  )
}
