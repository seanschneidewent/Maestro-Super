/**
 * Filename-only discipline classification for Google Drive imports.
 * Since Drive imports don't have folder paths, we rely solely on filename prefixes.
 * Falls back to 'general' for unrecognized patterns.
 */

import { DisciplineCode, getDisciplineDisplayName } from './disciplineClassifier';

export interface FilenameClassification {
  discipline: DisciplineCode;
  displayName: string;
}

/**
 * Prefix patterns for filename classification.
 * Order matters - check multi-character prefixes first.
 * Matches patterns like: "A-101", "A.1.01", "A101", "A 101"
 */
const PREFIX_PATTERNS: Array<{ pattern: RegExp; discipline: DisciplineCode }> = [
  // Multi-character prefixes first
  { pattern: /^VC[\s\-._]?\d/i, discipline: 'vapor_mitigation' },

  // Single-character prefixes
  { pattern: /^A[\s\-._]?\d/i, discipline: 'architectural' },
  { pattern: /^S[\s\-._]?\d/i, discipline: 'structural' },
  { pattern: /^M[\s\-._]?\d/i, discipline: 'mep' },
  { pattern: /^E[\s\-._]?\d/i, discipline: 'mep' },
  { pattern: /^P[\s\-._]?\d/i, discipline: 'mep' },
  { pattern: /^C[\s\-._]?\d/i, discipline: 'civil' },
  { pattern: /^K[\s\-._]?\d/i, discipline: 'kitchen' },
  { pattern: /^G[\s\-._]?\d/i, discipline: 'general' },
];

/**
 * Classify a file by its filename only.
 * Used for Google Drive imports where folder context is not available.
 *
 * @param filename - The filename (with or without extension)
 * @returns Classification with discipline code and display name
 *
 * @example
 * classifyByFilename('A-101.pdf') // { discipline: 'architectural', displayName: 'Architectural' }
 * classifyByFilename('S-201 Foundation.pdf') // { discipline: 'structural', displayName: 'Structural' }
 * classifyByFilename('random_document.pdf') // { discipline: 'general', displayName: 'General' }
 */
export function classifyByFilename(filename: string): FilenameClassification {
  // Remove extension for classification
  const baseName = filename.replace(/\.[^/.]+$/, '');

  // Check each prefix pattern
  for (const { pattern, discipline } of PREFIX_PATTERNS) {
    if (pattern.test(baseName)) {
      return {
        discipline,
        displayName: getDisciplineDisplayName(discipline),
      };
    }
  }

  // Default to 'general' for unrecognized patterns
  return {
    discipline: 'general',
    displayName: getDisciplineDisplayName('general'),
  };
}

/**
 * Classify multiple files by filename.
 * Groups files by their classified discipline.
 *
 * @param filenames - Array of filenames to classify
 * @returns Map of discipline codes to arrays of filenames
 */
export function classifyFilesByName(
  filenames: string[]
): Map<DisciplineCode, string[]> {
  const result = new Map<DisciplineCode, string[]>();

  for (const filename of filenames) {
    const { discipline } = classifyByFilename(filename);
    const existing = result.get(discipline) || [];
    existing.push(filename);
    result.set(discipline, existing);
  }

  return result;
}
