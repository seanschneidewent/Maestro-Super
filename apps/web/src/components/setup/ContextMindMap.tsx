import { useEffect, useRef, useState } from 'react';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';
import { api } from '../../lib/api';
import type { ProjectHierarchy, PageInHierarchy } from '../../types';

interface ContextMindMapProps {
  projectId: string;
  activePageId?: string;
  onPageClick?: (pageId: string) => void;
  refreshTrigger?: number;
}

const transformer = new Transformer();

function getPageIcon(page: PageInHierarchy): string {
  if (page.pointerCount === 0) return '\u25CB'; // ○
  if (!page.processedPass2) return '\u25D0'; // ◐
  return '\u25CF'; // ●
}

// Build lookup maps for click handling
interface HierarchyMaps {
  pageNameToId: Map<string, string>;
  disciplineNameToId: Map<string, string>;
}

function buildLookupMaps(data: ProjectHierarchy): HierarchyMaps {
  const pageNameToId = new Map<string, string>();
  const disciplineNameToId = new Map<string, string>();

  for (const disc of data.disciplines) {
    disciplineNameToId.set(disc.displayName, disc.id);
    for (const page of disc.pages) {
      pageNameToId.set(page.pageName, page.id);
    }
  }

  return { pageNameToId, disciplineNameToId };
}

function hierarchyToMarkdown(data: ProjectHierarchy, activePageId?: string): string {
  let md = `# ${data.name}\n`;

  for (const disc of data.disciplines) {
    const discIcon = disc.processed ? ' \u2605' : ''; // ★
    md += `## ${disc.displayName}${discIcon}\n`;

    for (const page of disc.pages) {
      const pageIcon = getPageIcon(page);
      const isActive = page.id === activePageId ? ' **' : '';
      md += `### ${page.pageName} ${pageIcon}${isActive}\n`;

      for (const ptr of page.pointers) {
        md += `- ${ptr.title}\n`;
      }
    }
  }

  return md;
}

export function ContextMindMap({
  projectId,
  activePageId,
  onPageClick,
  refreshTrigger,
}: ContextMindMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const markmapRef = useRef<Markmap | null>(null);
  const [hierarchy, setHierarchy] = useState<ProjectHierarchy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lookupMapsRef = useRef<HierarchyMaps | null>(null);

  // Fetch hierarchy (re-fetches when refreshTrigger changes)
  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.projects.getHierarchy(projectId);
        setHierarchy(data);
        lookupMapsRef.current = buildLookupMaps(data);
      } catch (err) {
        console.error('Failed to load hierarchy:', err);
        setError('Failed to load project hierarchy');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId, refreshTrigger]);

  // Parse page name from node content (e.g., "A1.01 ●" -> "A1.01")
  function extractPageName(nodeContent: string): string | null {
    // Node content format: "PageName ○|◐|●" or "PageName ○|◐|● **" (for active)
    const match = nodeContent.match(/^(.+?)\s*[\u25CB\u25D0\u25CF]/);
    return match ? match[1].trim() : null;
  }

  // Initialize and update Markmap
  useEffect(() => {
    if (!svgRef.current || !hierarchy) return;

    const md = hierarchyToMarkdown(hierarchy, activePageId);
    const { root } = transformer.transform(md);

    if (!markmapRef.current) {
      markmapRef.current = Markmap.create(svgRef.current, {
        autoFit: true,
        duration: 300,
        color: (node) => {
          if (node.depth === 0) return '#60a5fa'; // Project: blue
          if (node.depth === 1) return '#94a3b8'; // Discipline: slate
          if (node.depth === 2) return '#94a3b8'; // Page: slate
          return '#4ade80'; // Pointer: green
        },
        onClick: (node) => {
          // Only handle page-level clicks (depth 2)
          if (node.depth !== 2) return;

          const pageName = extractPageName(node.content || '');
          if (!pageName || !lookupMapsRef.current) return;

          const pageId = lookupMapsRef.current.pageNameToId.get(pageName);
          if (pageId && onPageClick) {
            onPageClick(pageId);
          }
        },
      });
    }

    markmapRef.current.setData(root);
    markmapRef.current.fit();
  }, [hierarchy, activePageId, onPageClick]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="animate-pulse">Loading hierarchy...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-400">
        {error}
      </div>
    );
  }

  if (!hierarchy || hierarchy.disciplines.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
        <p className="text-sm">No disciplines uploaded yet.</p>
        <p className="text-xs">Upload files to see the project hierarchy.</p>
      </div>
    );
  }

  return (
    <svg
      ref={svgRef}
      className="w-full h-full"
      style={{ minHeight: '400px', background: 'transparent' }}
    />
  );
}
