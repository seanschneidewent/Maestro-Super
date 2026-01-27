import { useState, useEffect } from 'react';

/**
 * Hook to detect virtual keyboard height on iOS/mobile.
 * Uses the visualViewport API to calculate how much the keyboard
 * has pushed up the visible area.
 *
 * Returns the keyboard height in pixels (0 when keyboard is closed).
 */
export function useKeyboardHeight(): number {
  const [keyboardHeight, setKeyboardHeight] = useState(0);

  useEffect(() => {
    // Only run on devices with visualViewport (iOS Safari, modern mobile browsers)
    const viewport = window.visualViewport;
    if (!viewport) return;

    const handleResize = () => {
      // Calculate keyboard height as difference between window height and viewport height
      // On iOS, when keyboard opens, visualViewport.height shrinks
      const newKeyboardHeight = Math.max(0, window.innerHeight - viewport.height);

      // Only consider it a keyboard if it's significant (> 100px)
      // This filters out small viewport changes from address bar hide/show
      if (newKeyboardHeight > 100) {
        setKeyboardHeight(newKeyboardHeight);
      } else {
        setKeyboardHeight(0);
      }
    };

    // Also handle scroll events - iOS can shift the viewport
    const handleScroll = () => {
      // On iOS, offsetTop indicates how much the viewport has scrolled
      // We need to account for this in our positioning
      handleResize();
    };

    viewport.addEventListener('resize', handleResize);
    viewport.addEventListener('scroll', handleScroll);

    // Initial check
    handleResize();

    return () => {
      viewport.removeEventListener('resize', handleResize);
      viewport.removeEventListener('scroll', handleScroll);
    };
  }, []);

  return keyboardHeight;
}
