import React from 'react';
import { Sparkles } from 'lucide-react';

const SUGGESTED_PROMPTS = [
  'Show me all canopy elevations.',
  'Take me to the building addition details so I can sequence this correctly.',
  'Show me fire specs and details.',
];

// Arrow component pointing right (to the button)
const TutorialArrow: React.FC = () => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 40 40"
    className="animate-[bounce_1s_infinite] text-cyan-500 flex-shrink-0"
    style={{ animationDirection: 'alternate' }}
  >
    <path
      d="M5 20 L30 20 M22 12 L30 20 L22 28"
      stroke="currentColor"
      strokeWidth="3"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

interface SuggestedPromptsProps {
  onSelectPrompt: (prompt: string) => void;
  disabled?: boolean;
  showTutorialArrows?: boolean;
}

export const SuggestedPrompts: React.FC<SuggestedPromptsProps> = ({
  onSelectPrompt,
  disabled = false,
  showTutorialArrows = false
}) => {
  return (
    <div className="flex flex-col gap-2 mb-3 animate-fade-in" data-tutorial="prompt-suggestions">
      <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-1">
        <Sparkles size={12} className="text-cyan-500" />
        <span>Try asking</span>
      </div>
      <div className="flex flex-col gap-2">
        {SUGGESTED_PROMPTS.map((prompt, index) => (
          <div key={index} className="flex items-center gap-2">
            {showTutorialArrows && <TutorialArrow />}
            <button
              onClick={() => onSelectPrompt(prompt)}
              disabled={disabled}
              className={`
                px-3 py-2 text-sm text-left
                bg-white/80 hover:bg-white
                border border-slate-200/80 hover:border-cyan-300
                rounded-xl shadow-sm hover:shadow
                text-slate-700 hover:text-slate-900
                transition-all duration-150
                disabled:opacity-50 disabled:cursor-not-allowed
                max-w-full
              `}
            >
              <span className="line-clamp-2">{prompt}</span>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
