import { useState, useRef, useCallback, useEffect } from 'react'
import { Mic, Loader2, Send, Square } from 'lucide-react'

interface QueryInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  isProcessing: boolean
  queryMode?: 'fast' | 'med' | 'deep'
  onQueryModeChange?: (mode: 'fast' | 'med' | 'deep') => void
  placeholder?: string
  onFocus?: () => void
}

// Get the SpeechRecognition constructor (browser-specific)
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition

export function QueryInput({
  value,
  onChange,
  onSubmit,
  isProcessing,
  queryMode = 'fast',
  onQueryModeChange,
  placeholder = 'Ask about your plans...',
  onFocus,
}: QueryInputProps) {
  const [isRecording, setIsRecording] = useState(false)
  const [isSupported, setIsSupported] = useState(true)
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  // Store the text that was in the input before recording started
  const preRecordingTextRef = useRef<string>('')

  const hasText = value.trim().length > 0

  // Check for browser support on mount
  useEffect(() => {
    if (!SpeechRecognition) {
      setIsSupported(false)
      console.warn('Speech recognition not supported in this browser')
    }
  }, [])

  const startRecording = useCallback(() => {
    if (isProcessing || !SpeechRecognition) return

    try {
      // Store current text before we start recording
      preRecordingTextRef.current = value

      const recognition = new SpeechRecognition()
      recognitionRef.current = recognition

      // Configure for live transcription
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let interimTranscript = ''
        let finalTranscript = ''

        // Process all results
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i]
          const transcript = result[0].transcript

          if (result.isFinal) {
            finalTranscript += transcript
          } else {
            interimTranscript += transcript
          }
        }

        // Combine pre-recording text with new transcription
        const prefix = preRecordingTextRef.current
        const separator = prefix && (finalTranscript || interimTranscript) ? ' ' : ''

        // Show interim results live, update with final when available
        const currentTranscript = finalTranscript || interimTranscript
        onChange(prefix + separator + currentTranscript)

        // If we got a final result, update the pre-recording text to include it
        if (finalTranscript) {
          preRecordingTextRef.current = prefix + separator + finalTranscript
        }
      }

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        console.error('Speech recognition error:', event.error)
        // Don't stop recording on 'no-speech' error - just keep listening
        if (event.error !== 'no-speech') {
          setIsRecording(false)
        }
      }

      recognition.onend = () => {
        setIsRecording(false)
      }

      recognition.start()
      setIsRecording(true)
    } catch (error) {
      console.error('Failed to start speech recognition:', error)
      setIsRecording(false)
    }
  }, [isProcessing, value, onChange])

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      recognitionRef.current = null
      setIsRecording(false)
    }
  }, [])

  const handleButtonClick = () => {
    if (isProcessing || !isSupported) return

    if (isRecording) {
      // Currently recording - stop it
      stopRecording()
    } else if (hasText) {
      // Has text and not recording - send it
      onSubmit()
    } else {
      // No text and not recording - start recording
      startRecording()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && hasText && !isProcessing && !isRecording) {
      e.preventDefault()
      onSubmit()
    }
  }

  // Button size matches the pill height for seamless integration
  const buttonSize = 52
  const nextMode = queryMode === 'fast' ? 'med' : queryMode === 'med' ? 'deep' : 'fast'

  // Determine button state and icon
  const getButtonContent = () => {
    if (isProcessing) {
      return <Loader2 size={24} className="text-slate-400 animate-spin" />
    }
    if (isRecording) {
      return <Square size={18} className="text-white fill-white" />
    }
    if (hasText) {
      return <Send size={22} className="text-white" />
    }
    return <Mic size={24} className="text-slate-500" />
  }

  const getButtonStyle = () => {
    if (isProcessing) return 'bg-slate-200 cursor-not-allowed'
    if (!isSupported) return 'bg-slate-200 cursor-not-allowed opacity-50'
    if (isRecording) return 'bg-red-500 hover:bg-red-600'
    if (hasText) return 'bg-cyan-500 hover:bg-cyan-600'
    return 'bg-slate-100 hover:bg-slate-200'
  }

  return (
    <div
      className={`
        flex items-center
        bg-white/90 backdrop-blur-md
        border border-cyan-300/40
        rounded-full
        shadow-glow-cyan animate-glow-pulse
        transition-all duration-150
        ${isRecording ? 'ring-2 ring-red-500' : ''}
      `}
      style={{ paddingLeft: 20, paddingRight: 5, paddingTop: 5, paddingBottom: 5 }}
    >
      {/* Text input */}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={onFocus}
        placeholder={isRecording ? 'Listening...' : placeholder}
        disabled={isProcessing}
        className={`
          flex-1 bg-transparent text-slate-800 placeholder:text-slate-400
          outline-none text-base min-w-0
          ${isRecording ? 'placeholder:text-red-400' : ''}
        `}
      />

      {/* Fast/Deep mode toggle */}
      {onQueryModeChange && (
        <button
          type="button"
          onClick={() => onQueryModeChange(nextMode)}
          disabled={isProcessing}
          title={`${queryMode.charAt(0).toUpperCase()}${queryMode.slice(1)} mode enabled`}
          className={`
            flex-shrink-0 rounded-full px-3 mr-2
            text-xs font-semibold uppercase tracking-wide
            transition-all duration-150
            ${isProcessing ? 'bg-slate-200 text-slate-400 cursor-not-allowed' : ''}
            ${
              !isProcessing && queryMode === 'deep'
                ? 'bg-cyan-500 text-white hover:bg-cyan-600'
                : ''
            }
            ${
              !isProcessing && queryMode === 'med'
                ? 'bg-amber-400 text-amber-900 hover:bg-amber-500'
                : ''
            }
            ${
              !isProcessing && queryMode === 'fast'
                ? 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                : ''
            }
          `}
          style={{ height: buttonSize }}
        >
          {queryMode === 'deep' ? 'Deep' : queryMode === 'med' ? 'Med' : 'Fast'}
        </button>
      )}

      {/* Action button - Mic / Stop / Send */}
      <button
        type="button"
        onClick={handleButtonClick}
        disabled={isProcessing || !isSupported}
        title={
          !isSupported
            ? 'Speech recognition not supported in this browser'
            : isRecording
            ? 'Tap to stop recording'
            : hasText
            ? 'Send message'
            : 'Tap to start recording'
        }
        className={`
          flex-shrink-0 rounded-full
          flex items-center justify-center
          transition-all duration-150
          select-none
          ${getButtonStyle()}
        `}
        style={{ width: buttonSize, height: buttonSize }}
      >
        {getButtonContent()}
      </button>
    </div>
  )
}

// Keep the old export for backwards compatibility during transition
export const HoldToTalk = QueryInput
