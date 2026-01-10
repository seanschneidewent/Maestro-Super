import React, { createContext, useState, useCallback, ReactNode } from 'react';
import { TutorialStep } from '../../types';

const STORAGE_KEY = 'maestro-tutorial-completed';

interface TutorialContextValue {
  currentStep: TutorialStep;
  isActive: boolean;
  hasCompleted: boolean;
  advanceStep: () => void;
  skipTutorial: () => void;
  completeStep: (step: TutorialStep) => void;
}

export const TutorialContext = createContext<TutorialContextValue | null>(null);

const STEP_ORDER: NonNullable<TutorialStep>[] = [
  'welcome', 'sidebar', 'viewer', 'query', 'responding',
  'new-session', 'session-intro', 'history', 'complete'
];

// Check localStorage synchronously to avoid flash of wrong state
const getInitialTutorialState = () => {
  const completed = localStorage.getItem(STORAGE_KEY) === 'true';
  return {
    hasCompleted: completed,
    isActive: !completed,
    currentStep: completed ? null : ('welcome' as TutorialStep),
  };
};

export const TutorialProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const initialState = getInitialTutorialState();
  const [currentStep, setCurrentStep] = useState<TutorialStep>(initialState.currentStep);
  const [isActive, setIsActive] = useState(initialState.isActive);
  const [hasCompleted, setHasCompleted] = useState(initialState.hasCompleted);

  const advanceStep = useCallback(() => {
    setCurrentStep(prev => {
      const currentIndex = prev ? STEP_ORDER.indexOf(prev) : -1;
      const nextIndex = currentIndex + 1;
      if (nextIndex >= STEP_ORDER.length) {
        // Tutorial complete
        localStorage.setItem(STORAGE_KEY, 'true');
        setHasCompleted(true);
        setIsActive(false);
        return null;
      }
      return STEP_ORDER[nextIndex];
    });
  }, []);

  const completeStep = useCallback((step: TutorialStep) => {
    if (currentStep === step) {
      advanceStep();
    }
  }, [currentStep, advanceStep]);

  const skipTutorial = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setHasCompleted(true);
    setIsActive(false);
    setCurrentStep(null);
  }, []);

  return (
    <TutorialContext.Provider value={{
      currentStep,
      isActive,
      hasCompleted,
      advanceStep,
      skipTutorial,
      completeStep,
    }}>
      {children}
    </TutorialContext.Provider>
  );
};
