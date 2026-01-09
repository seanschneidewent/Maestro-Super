import { useContext } from 'react';
import { TutorialContext } from '../components/tutorial/TutorialProvider';
import { TutorialStep } from '../types';

export function useTutorial() {
  const context = useContext(TutorialContext);
  if (!context) {
    // Return inactive state when outside provider
    return {
      currentStep: null as TutorialStep,
      isActive: false,
      hasCompleted: true,
      advanceStep: () => {},
      skipTutorial: () => {},
      completeStep: (_step: TutorialStep) => {},
    };
  }
  return context;
}
