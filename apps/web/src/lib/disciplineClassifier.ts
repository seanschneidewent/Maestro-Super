/**
 * Discipline classification for construction plan files.
 * Uses folder names and file prefixes to determine discipline.
 */

export type DisciplineCode =
  | 'architectural'
  | 'structural'
  | 'mep'
  | 'civil'
  | 'kitchen'
  | 'vapor_mitigation'
  | 'canopy'
  | 'general'
  | 'unknown';

export type ClassificationConfidence = 'high' | 'needs_review';

export interface DisciplineClassification {
  discipline: DisciplineCode;
  confidence: ClassificationConfidence;
  source: 'folder' | 'prefix' | 'none';
  conflictReason?: string;
}

export interface ClassifiedFile {
  file: File;
  relativePath: string;
  fileName: string;
  classification: DisciplineClassification;
}

export interface UploadPlan {
  projectName: string;
  disciplines: Map<DisciplineCode, ClassifiedFile[]>;
  filesNeedingReview: ClassifiedFile[];
  totalFileCount: number;
}

const DISCIPLINE_DISPLAY_NAMES: Record<DisciplineCode, string> = {
  architectural: 'Architectural',
  structural: 'Structural',
  mep: 'MEP',
  civil: 'Civil',
  kitchen: 'Kitchen',
  vapor_mitigation: 'Vapor Mitigation',
  canopy: 'Canopy',
  general: 'General',
  unknown: 'Unknown',
};

// Folder name patterns (case-insensitive)
const FOLDER_PATTERNS: Array<{ pattern: RegExp; discipline: DisciplineCode }> = [
  { pattern: /arch/i, discipline: 'architectural' },
  { pattern: /struct/i, discipline: 'structural' },
  { pattern: /mep/i, discipline: 'mep' },
  { pattern: /civil/i, discipline: 'civil' },
  { pattern: /kitchen/i, discipline: 'kitchen' },
  { pattern: /vapor/i, discipline: 'vapor_mitigation' },
  { pattern: /canopy/i, discipline: 'canopy' },
];

// File prefix patterns (sorted by length for multi-char prefixes first)
const PREFIX_PATTERNS: Array<{ prefixes: string[]; discipline: DisciplineCode }> = [
  { prefixes: ['VC'], discipline: 'vapor_mitigation' }, // Check VC before V
  { prefixes: ['A'], discipline: 'architectural' },
  { prefixes: ['S'], discipline: 'structural' },
  { prefixes: ['M', 'E', 'P'], discipline: 'mep' },
  { prefixes: ['C'], discipline: 'civil' },
  { prefixes: ['K'], discipline: 'kitchen' },
  { prefixes: ['G'], discipline: 'general' },
  // Note: 'canopy' has no prefix pattern - folder only
];

// Files to skip during classification
const SKIP_PATTERNS = [
  /^\./,           // Hidden files (.DS_Store, etc.)
  /^__/,           // Python cache, etc.
  /thumbs\.db$/i,  // Windows thumbnails
];

function shouldSkipFile(fileName: string): boolean {
  return SKIP_PATTERNS.some(pattern => pattern.test(fileName));
}

export function classifyFromFolder(folderName: string): DisciplineCode | null {
  for (const { pattern, discipline } of FOLDER_PATTERNS) {
    if (pattern.test(folderName)) {
      return discipline;
    }
  }
  return null;
}

export function classifyFromPrefix(fileName: string): DisciplineCode | null {
  // Extract the base name without extension
  const baseName = fileName.replace(/\.[^/.]+$/, '');

  // Check for multi-character prefixes first (VC before V, etc.)
  for (const { prefixes, discipline } of PREFIX_PATTERNS) {
    // Sort prefixes by length descending to match longer ones first
    const sortedPrefixes = [...prefixes].sort((a, b) => b.length - a.length);
    for (const prefix of sortedPrefixes) {
      if (baseName.toUpperCase().startsWith(prefix)) {
        return discipline;
      }
    }
  }
  return null;
}

export function classifyFile(
  fileName: string,
  folderName: string | null
): DisciplineClassification {
  const folderDiscipline = folderName ? classifyFromFolder(folderName) : null;
  const prefixDiscipline = classifyFromPrefix(fileName);

  // Case 1: Both match
  if (folderDiscipline && prefixDiscipline) {
    if (folderDiscipline === prefixDiscipline) {
      return {
        discipline: folderDiscipline,
        confidence: 'high',
        source: 'folder',
      };
    } else {
      // Conflict - flag for review, prefer prefix as it's more specific
      return {
        discipline: prefixDiscipline,
        confidence: 'needs_review',
        source: 'prefix',
        conflictReason: `Folder suggests "${DISCIPLINE_DISPLAY_NAMES[folderDiscipline]}" but filename prefix suggests "${DISCIPLINE_DISPLAY_NAMES[prefixDiscipline]}"`,
      };
    }
  }

  // Case 2: Only folder match
  if (folderDiscipline) {
    return {
      discipline: folderDiscipline,
      confidence: 'high',
      source: 'folder',
    };
  }

  // Case 3: Only prefix match
  if (prefixDiscipline) {
    return {
      discipline: prefixDiscipline,
      confidence: 'high',
      source: 'prefix',
    };
  }

  // Case 4: No match
  return {
    discipline: 'unknown',
    confidence: 'needs_review',
    source: 'none',
    conflictReason: 'Could not determine discipline from folder name or file prefix',
  };
}

/**
 * Build an upload plan from selected files.
 * Groups files by discipline and identifies those needing review.
 */
export function buildUploadPlan(files: FileList): UploadPlan {
  const disciplineMap = new Map<DisciplineCode, ClassifiedFile[]>();
  const filesNeedingReview: ClassifiedFile[] = [];

  // Extract project name from root folder
  let projectName = 'Untitled Project';
  if (files.length > 0) {
    const firstPath = files[0].webkitRelativePath;
    const rootFolder = firstPath.split('/')[0];
    projectName = rootFolder || projectName;
  }

  let validFileCount = 0;

  for (const file of Array.from(files)) {
    const relativePath = file.webkitRelativePath;
    const pathParts = relativePath.split('/');

    // Skip system files and non-PDFs
    if (shouldSkipFile(file.name)) continue;
    if (!file.name.toLowerCase().endsWith('.pdf')) continue;

    validFileCount++;

    // Get immediate parent folder (not root)
    // If path is "ProjectName/Architectural/A1.01.pdf", we want "Architectural"
    const folderName = pathParts.length > 2 ? pathParts[pathParts.length - 2] : null;

    const classification = classifyFile(file.name, folderName);
    const classifiedFile: ClassifiedFile = {
      file,
      relativePath,
      fileName: file.name,
      classification,
    };

    // Track files needing review
    if (classification.confidence === 'needs_review') {
      filesNeedingReview.push(classifiedFile);
    }

    // Add to discipline map
    const existing = disciplineMap.get(classification.discipline) || [];
    existing.push(classifiedFile);
    disciplineMap.set(classification.discipline, existing);
  }

  return {
    projectName,
    disciplines: disciplineMap,
    filesNeedingReview,
    totalFileCount: validFileCount,
  };
}

/**
 * Get display name for a discipline code.
 */
export function getDisciplineDisplayName(code: DisciplineCode): string {
  return DISCIPLINE_DISPLAY_NAMES[code];
}

/**
 * Derive page name from filename.
 * Removes extension and cleans up the name.
 */
export function derivePageName(fileName: string): string {
  // Remove extension: "A1.01 - Floor Plan.pdf" -> "A1.01 - Floor Plan"
  return fileName.replace(/\.[^/.]+$/, '');
}

/**
 * Convert UploadPlan to the format expected by the API.
 */
export function planToApiRequest(
  plan: UploadPlan,
  uploadedPaths: Map<string, string> // relativePath -> storagePath
): {
  projectName: string;
  disciplines: Array<{
    code: DisciplineCode;
    displayName: string;
    pages: Array<{
      pageName: string;
      fileName: string;
      storagePath: string;
    }>;
  }>;
} {
  const disciplines: Array<{
    code: DisciplineCode;
    displayName: string;
    pages: Array<{
      pageName: string;
      fileName: string;
      storagePath: string;
    }>;
  }> = [];

  for (const [code, files] of plan.disciplines) {
    const pages = files
      .map(cf => {
        const storagePath = uploadedPaths.get(cf.relativePath);
        if (!storagePath) return null;
        return {
          pageName: derivePageName(cf.fileName),
          fileName: cf.fileName,
          storagePath,
        };
      })
      .filter((p): p is NonNullable<typeof p> => p !== null);

    if (pages.length > 0) {
      disciplines.push({
        code,
        displayName: getDisciplineDisplayName(code),
        pages,
      });
    }
  }

  return {
    projectName: plan.projectName,
    disciplines,
  };
}
