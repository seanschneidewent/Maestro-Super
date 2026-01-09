/**
 * Google Drive Import Button for Setup Mode.
 * Only visible for users who signed in with Google OAuth.
 * Downloads selected PDFs from Drive and prepares them for upload.
 */

import React, { useState } from 'react';
import { Cloud, Loader2 } from 'lucide-react';
import { useGoogleDrivePicker, DriveFile } from '../../hooks/useGoogleDrivePicker';
import { classifyByFilename } from '../../lib/classifyByFilename';
import { DisciplineCode } from '../../lib/disciplineClassifier';
import { useToast } from '../ui/Toast';

const MAX_FILE_SIZE_MB = 50;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

export interface DriveImportFile {
  file: File;
  discipline: DisciplineCode;
  displayName: string;
}

interface DriveImportButtonProps {
  disabled?: boolean;
  onFilesSelected: (files: DriveImportFile[]) => Promise<void>;
}

export const DriveImportButton: React.FC<DriveImportButtonProps> = ({
  disabled = false,
  onFilesSelected,
}) => {
  const { hasGoogleToken, isLoaded, isLoading: pickerLoading, openPicker, getToken } =
    useGoogleDrivePicker();
  const { showError, showWarning, showSuccess } = useToast();
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<string>('');

  // Hide button entirely if user didn't sign in with Google
  if (!hasGoogleToken) {
    return null;
  }

  const downloadDriveFile = async (
    file: DriveFile,
    token: string
  ): Promise<File | null> => {
    // Check file size
    if (file.sizeBytes && file.sizeBytes > MAX_FILE_SIZE_BYTES) {
      showWarning(
        `Skipped "${file.name}" - file is too large (${Math.round(file.sizeBytes / 1024 / 1024)}MB, max ${MAX_FILE_SIZE_MB}MB)`
      );
      return null;
    }

    const response = await fetch(
      `https://www.googleapis.com/drive/v3/files/${file.id}?alt=media`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    );

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('TOKEN_EXPIRED');
      }
      throw new Error(`Failed to download "${file.name}": ${response.statusText}`);
    }

    const blob = await response.blob();
    return new File([blob], file.name, { type: 'application/pdf' });
  };

  const handleClick = async () => {
    if (!isLoaded) {
      showError('Google Drive is still loading. Please try again in a moment.');
      return;
    }

    try {
      // Open picker and get selected files
      const selectedFiles = await openPicker();

      if (selectedFiles.length === 0) {
        return; // User cancelled
      }

      setIsDownloading(true);

      // Get fresh token
      let token = await getToken();
      if (!token) {
        showError('Unable to access Google Drive. Please sign in again with Google.');
        setIsDownloading(false);
        return;
      }

      const importedFiles: DriveImportFile[] = [];
      let retried = false;

      for (let i = 0; i < selectedFiles.length; i++) {
        const driveFile = selectedFiles[i];
        setDownloadProgress(`Downloading ${i + 1}/${selectedFiles.length}: ${driveFile.name}`);

        try {
          const file = await downloadDriveFile(driveFile, token);

          if (file) {
            // Classify by filename
            const { discipline, displayName } = classifyByFilename(file.name);
            importedFiles.push({ file, discipline, displayName });
          }
        } catch (err) {
          // Handle token expiration with one retry
          if (err instanceof Error && err.message === 'TOKEN_EXPIRED' && !retried) {
            retried = true;
            token = await getToken();
            if (!token) {
              showError('Session expired. Please sign in again with Google.');
              break;
            }
            // Retry this file
            i--;
            continue;
          }

          // Show error and continue with other files
          if (err instanceof Error) {
            showError(err.message);
          }
        }
      }

      setDownloadProgress('');

      if (importedFiles.length > 0) {
        await onFilesSelected(importedFiles);
        showSuccess(`Imported ${importedFiles.length} file${importedFiles.length > 1 ? 's' : ''} from Google Drive`);
      } else if (selectedFiles.length > 0) {
        showWarning('No files were imported. All files may have been too large or failed to download.');
      }
    } catch (err) {
      console.error('Drive import error:', err);
      showError(
        err instanceof Error
          ? err.message
          : 'Failed to import files from Google Drive'
      );
    } finally {
      setIsDownloading(false);
      setDownloadProgress('');
    }
  };

  const isDisabled = disabled || !isLoaded || pickerLoading || isDownloading;

  return (
    <button
      onClick={handleClick}
      disabled={isDisabled}
      className="w-full py-3.5 rounded-lg bg-gradient-to-r from-cyan-600/20 to-blue-600/20 border border-cyan-500/30 text-cyan-200 text-sm font-medium hover:border-cyan-400/50 hover:from-cyan-600/30 hover:to-blue-600/30 transition-all shadow-lg shadow-cyan-900/10 group disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {isDownloading ? (
        <span className="flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="truncate max-w-[200px]">{downloadProgress || 'Importing...'}</span>
        </span>
      ) : pickerLoading ? (
        <span className="flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Opening Drive...
        </span>
      ) : !isLoaded ? (
        <span className="flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading Drive...
        </span>
      ) : (
        <span className="flex items-center justify-center gap-2 group-hover:drop-shadow-[0_0_8px_rgba(6,182,212,0.5)] transition-all">
          <Cloud className="w-4 h-4" />
          Import from Google Drive
        </span>
      )}
    </button>
  );
};
