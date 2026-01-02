import { useEffect, useRef, useState } from 'react';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';
import { api } from '../../lib/api';
import type { ProjectHierarchy, PageInHierarchy } from '../../types';

interface ContextMindMapProps {
  projectId: string;
  activePageId?: string;
  onPageClick?: (pageId: string, disciplineId: string) => void;
  onPointerClick?: (pointerId: string, pageId: string) => void;
  onDisciplineClick?: (disciplineId: string) => void;
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
  pageIdToDisciplineId: Map<string, string>;
  disciplineNameToId: Map<string, string>;
  // Key: "${pageName}:${pointerTitle}" to avoid collision if same title on different pages
  pointerKeyToData: Map<string, { pointerId: string; pageId: string }>;
}

function buildLookupMaps(data: ProjectHierarchy): HierarchyMaps {
  const pageNameToId = new Map<string, string>();
  const pageIdToDisciplineId = new Map<string, string>();
  const disciplineNameToId = new Map<string, string>();
  const pointerKeyToData = new Map<string, { pointerId: string; pageId: string }>();

  for (const disc of data.disciplines) {
    disciplineNameToId.set(disc.displayName, disc.id);
    for (const page of disc.pages) {
      pageNameToId.set(page.pageName, page.id);
      pageIdToDisciplineId.set(page.id, disc.id);
      for (const ptr of page.pointers) {
        const key = `${page.pageName}:${ptr.title}`;
        pointerKeyToData.set(key, { pointerId: ptr.id, pageId: page.id });
      }
    }
  }

  return { pageNameToId, pageIdToDisciplineId, disciplineNameToId, pointerKeyToData };
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
  onPointerClick,
  onDisciplineClick,
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

  // Parse discipline name from node content (e.g., "Architectural ★" -> "Architectural")
  function extractDisciplineName(nodeContent: string): string | null {
    // Remove star icon if present
    const cleaned = nodeContent.replace(/\s*\u2605\s*$/, '').trim();
    return cleaned || null;
  }

  // Parse page name from node content (e.g., "A1.01 ●" -> "A1.01")
  function extractPageName(nodeContent: string): string | null {
    // Node content format: "PageName ○|◐|●" or "PageName ○|◐|● **" (for active)
    const match = nodeContent.match(/^(.+?)\s*[\u25CB\u25D0\u25CF]/);
    return match ? match[1].trim() : null;
  }

  // Parse pointer title from node content (e.g., "- Electrical Panel" -> "Electrical Panel")
  function extractPointerTitle(nodeContent: string): string | null {
    // List item format: "- Title" or just the title (Markmap strips the -)
    const match = nodeContent.match(/^-?\s*(.+)$/);
    return match ? match[1].trim() : null;
  }

  // Track current page name for pointer lookup (set when traversing to depth 2)
  const currentPageNameRef = useRef<string | null>(null);

  // Handle node click - use callback refs to avoid stale closures
  const handlersRef = useRef({
    onPageClick,
    onPointerClick,
    onDisciplineClick,
  });

  useEffect(() => {
    handlersRef.current = { onPageClick, onPointerClick, onDisciplineClick };
  }, [onPageClick, onPointerClick, onDisciplineClick]);

  const handleNodeClick = (nodeData: any) => {
    if (!lookupMapsRef.current) return;
    const maps = lookupMapsRef.current;
    const depth = nodeData.depth;
    const content = nodeData.content || '';

    if (depth === 1) {
      // Discipline click
      const discName = extractDisciplineName(content);
      if (!discName) return;
      const discId = maps.disciplineNameToId.get(discName);
      if (discId && handlersRef.current.onDisciplineClick) {
        handlersRef.current.onDisciplineClick(discId);
      }
    } else if (depth === 2) {
      // Page click
      const pageName = extractPageName(content);
      if (!pageName) return;
      const pageId = maps.pageNameToId.get(pageName);
      const discId = pageId ? maps.pageIdToDisciplineId.get(pageId) : undefined;
      if (pageId && handlersRef.current.onPageClick) {
        handlersRef.current.onPageClick(pageId, discId || '');
      }
    } else if (depth === 3) {
      // Pointer click - need to find parent page name
      const pointerTitle = extractPointerTitle(content);
      if (!pointerTitle) return;

      // Traverse up to find parent page node
      let parentNode = nodeData.parent;
      while (parentNode && parentNode.depth !== 2) {
        parentNode = parentNode.parent;
      }
      if (!parentNode) return;

      const pageName = extractPageName(parentNode.content || '');
      if (!pageName) return;

      const key = `${pageName}:${pointerTitle}`;
      const ptrData = maps.pointerKeyToData.get(key);
      if (ptrData && handlersRef.current.onPointerClick) {
        handlersRef.current.onPointerClick(ptrData.pointerId, ptrData.pageId);
      }
    }
  };

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
      });
    }

    markmapRef.current.setData(root);
    markmapRef.current.fit();

    // Add click handlers to nodes after rendering
    // Markmap uses d3 to render, so we need to wait for the render to complete
    setTimeout(() => {
      if (!svgRef.current) return;

      // Query all node groups
      const nodeGroups = svgRef.current.querySelectorAll('g.markmap-node');
      nodeGroups.forEach((g) => {
        // Get the bound data from the d3 selection
        const d3Node = (g as any).__data__;
        if (!d3Node || d3Node.depth === 0) return; // Skip root node

        // Make the node look clickable
        (g as HTMLElement).style.cursor = 'pointer';

        // Use data attribute to mark as initialized to avoid duplicate handlers
        if (g.getAttribute('data-click-init')) return;
        g.setAttribute('data-click-init', 'true');

        // Add single click handler to the group element
        g.addEventListener('click', (e: Event) => {
          e.stopPropagation();
          // Re-read __data__ at click time in case it changed
          const nodeData = (g as any).__data__;
          if (nodeData) {
            handleNodeClick(nodeData);
          }
        });
      });
    }, 350); // Wait for markmap animation to complete
  }, [hierarchy, activePageId]);

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
