/**
 * Hook for integrating Google Drive Picker for file selection.
 * Only works for users who signed in with Google OAuth.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { supabase } from '../lib/supabase';

declare global {
  interface Window {
    gapi: {
      load: (api: string, callback: (() => void) | { callback: () => void; onerror?: () => void }) => void;
      client: {
        init: (config: object) => Promise<void>;
        getToken: () => { access_token: string } | null;
        setToken: (token: { access_token: string }) => void;
      };
    };
    google: {
      picker: {
        PickerBuilder: new () => GooglePickerBuilder;
        ViewId: {
          DOCS: string;
          PDFS: string;
        };
        Feature: {
          MULTISELECT_ENABLED: string;
          NAV_HIDDEN: string;
        };
        Action: {
          PICKED: string;
          CANCEL: string;
        };
        DocsView: new (viewId?: string) => GoogleDocsView;
      };
    };
  }
}

interface GoogleDocsView {
  setMimeTypes: (mimeTypes: string) => GoogleDocsView;
  setIncludeFolders: (include: boolean) => GoogleDocsView;
}

interface GooglePickerBuilder {
  addView: (view: GoogleDocsView) => GooglePickerBuilder;
  enableFeature: (feature: string) => GooglePickerBuilder;
  setOAuthToken: (token: string) => GooglePickerBuilder;
  setDeveloperKey: (key: string) => GooglePickerBuilder;
  setCallback: (callback: (data: PickerCallbackData) => void) => GooglePickerBuilder;
  setOrigin: (origin: string) => GooglePickerBuilder;
  build: () => { setVisible: (visible: boolean) => void };
}

interface PickerCallbackData {
  action: string;
  docs?: Array<{
    id: string;
    name: string;
    mimeType: string;
    sizeBytes?: number;
  }>;
}

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes?: number;
}

interface UseGoogleDrivePickerResult {
  /** Whether the user has a Google provider token (signed in with Google) */
  hasGoogleToken: boolean;
  /** Whether the Google Picker API is loaded */
  isLoaded: boolean;
  /** Whether the picker is currently loading */
  isLoading: boolean;
  /** Error message if any */
  error: string | null;
  /** Open the Google Picker and return selected files */
  openPicker: () => Promise<DriveFile[]>;
  /** Get the current Google OAuth token */
  getToken: () => Promise<string | null>;
}

const GOOGLE_API_KEY = import.meta.env.VITE_GOOGLE_API_KEY;
const PICKER_SCRIPT_URL = 'https://apis.google.com/js/api.js';

let scriptLoadPromise: Promise<void> | null = null;

function loadGoogleScript(): Promise<void> {
  if (scriptLoadPromise) return scriptLoadPromise;

  scriptLoadPromise = new Promise((resolve, reject) => {
    // Check if already loaded
    if (window.gapi) {
      resolve();
      return;
    }

    const script = document.createElement('script');
    script.src = PICKER_SCRIPT_URL;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Google API script'));
    document.head.appendChild(script);
  });

  return scriptLoadPromise;
}

function loadPickerApi(): Promise<void> {
  return new Promise((resolve, reject) => {
    window.gapi.load('picker', {
      callback: resolve,
      onerror: () => reject(new Error('Failed to load Google Picker API')),
    });
  });
}

export function useGoogleDrivePicker(): UseGoogleDrivePickerResult {
  const [hasGoogleToken, setHasGoogleToken] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tokenRef = useRef<string | null>(null);

  // Check for Google provider token on mount
  useEffect(() => {
    async function checkToken() {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.provider_token) {
        tokenRef.current = session.provider_token;
        setHasGoogleToken(true);
      } else {
        setHasGoogleToken(false);
      }
    }
    checkToken();

    // Subscribe to auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (_event, session) => {
        if (session?.provider_token) {
          tokenRef.current = session.provider_token;
          setHasGoogleToken(true);
        } else {
          tokenRef.current = null;
          setHasGoogleToken(false);
        }
      }
    );

    return () => subscription.unsubscribe();
  }, []);

  // Load Google Picker API when token is available
  useEffect(() => {
    if (!hasGoogleToken || !GOOGLE_API_KEY) return;

    async function loadApi() {
      try {
        await loadGoogleScript();
        await loadPickerApi();
        setIsLoaded(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load Google APIs');
      }
    }

    loadApi();
  }, [hasGoogleToken]);

  const getToken = useCallback(async (): Promise<string | null> => {
    // Try to get fresh token
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.provider_token) {
      tokenRef.current = session.provider_token;
      return session.provider_token;
    }

    // Try to refresh the session
    const { data: { session: refreshedSession }, error: refreshError } =
      await supabase.auth.refreshSession();

    if (refreshError) {
      console.error('Failed to refresh session:', refreshError);
      return null;
    }

    if (refreshedSession?.provider_token) {
      tokenRef.current = refreshedSession.provider_token;
      return refreshedSession.provider_token;
    }

    return null;
  }, []);

  const openPicker = useCallback(async (): Promise<DriveFile[]> => {
    if (!isLoaded) {
      throw new Error('Google Picker API not loaded');
    }

    if (!GOOGLE_API_KEY) {
      throw new Error('Google API key not configured');
    }

    setIsLoading(true);
    setError(null);

    try {
      const token = await getToken();
      if (!token) {
        throw new Error('No Google OAuth token available. Please sign in with Google.');
      }

      return new Promise((resolve, reject) => {
        // Create a view for PDF files
        const docsView = new window.google.picker.DocsView()
          .setMimeTypes('application/pdf')
          .setIncludeFolders(true);

        // Build the picker
        const picker = new window.google.picker.PickerBuilder()
          .addView(docsView)
          .enableFeature(window.google.picker.Feature.MULTISELECT_ENABLED)
          .setOAuthToken(token)
          .setDeveloperKey(GOOGLE_API_KEY)
          .setOrigin(window.location.origin)
          .setCallback((data: PickerCallbackData) => {
            if (data.action === window.google.picker.Action.PICKED) {
              const files: DriveFile[] = (data.docs || []).map((doc) => ({
                id: doc.id,
                name: doc.name,
                mimeType: doc.mimeType,
                sizeBytes: doc.sizeBytes,
              }));
              setIsLoading(false);
              resolve(files);
            } else if (data.action === window.google.picker.Action.CANCEL) {
              setIsLoading(false);
              resolve([]);
            }
          })
          .build();

        picker.setVisible(true);
      });
    } catch (err) {
      setIsLoading(false);
      const message = err instanceof Error ? err.message : 'Failed to open picker';
      setError(message);
      throw err;
    }
  }, [isLoaded, getToken]);

  return {
    hasGoogleToken,
    isLoaded,
    isLoading,
    error,
    openPicker,
    getToken,
  };
}
