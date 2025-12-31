import { supabase } from './supabase';

const BUCKET_NAME = 'project-files';

export interface UploadResult {
  storagePath: string;
  publicUrl: string;
}

/**
 * Upload a file to Supabase Storage
 * @param projectId - Project ID for organizing files
 * @param file - File object to upload
 * @param relativePath - Optional relative path within project folder
 * @returns Storage path and public URL
 */
export async function uploadFile(
  projectId: string,
  file: File,
  relativePath?: string
): Promise<UploadResult> {
  // Build storage path: projects/{projectId}/{relativePath or filename}
  const fileName = relativePath || file.name;
  const storagePath = `projects/${projectId}/${fileName}`;

  const { error } = await supabase.storage
    .from(BUCKET_NAME)
    .upload(storagePath, file, {
      cacheControl: '3600',
      upsert: true, // Overwrite if exists
    });

  if (error) {
    throw new Error(`Upload failed: ${error.message}`);
  }

  // Get public URL
  const { data: { publicUrl } } = supabase.storage
    .from(BUCKET_NAME)
    .getPublicUrl(storagePath);

  return { storagePath, publicUrl };
}

/**
 * Download a file from Supabase Storage
 * @param storagePath - Path in storage bucket
 * @returns File blob
 */
export async function downloadFile(storagePath: string): Promise<Blob> {
  const { data, error } = await supabase.storage
    .from(BUCKET_NAME)
    .download(storagePath);

  if (error) {
    throw new Error(`Download failed: ${error.message}`);
  }

  return data;
}

/**
 * Get a signed URL for private file access
 * @param storagePath - Path in storage bucket
 * @param expiresIn - Seconds until URL expires (default 1 hour)
 * @returns Signed URL
 */
export async function getSignedUrl(
  storagePath: string,
  expiresIn = 3600
): Promise<string> {
  const { data, error } = await supabase.storage
    .from(BUCKET_NAME)
    .createSignedUrl(storagePath, expiresIn);

  if (error) {
    throw new Error(`Failed to create signed URL: ${error.message}`);
  }

  return data.signedUrl;
}

/**
 * Delete a file from Supabase Storage
 * @param storagePath - Path in storage bucket
 */
export async function deleteFile(storagePath: string): Promise<void> {
  const { error } = await supabase.storage
    .from(BUCKET_NAME)
    .remove([storagePath]);

  if (error) {
    throw new Error(`Delete failed: ${error.message}`);
  }
}

/**
 * Convert a Blob to a File object
 * @param blob - Blob to convert
 * @param filename - Name for the File
 * @returns File object
 */
export function blobToFile(blob: Blob, filename: string): File {
  return new File([blob], filename, { type: blob.type });
}
