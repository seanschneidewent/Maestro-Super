import { useContext } from 'react';
import { TutorialContext } from '../components/tutorial/TutorialProvider';
import { TutorialStep } from '../types';

export function useTutorial() {
  const context = useContext(TutorialContext);
  if (!context) {
    console.log('[useTutorial] No context found, returning inactive state');
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
  console.log('[useTutorial] Context found:', { currentStep: context.currentStep, isActive: context.isActive });
  return context;
}
