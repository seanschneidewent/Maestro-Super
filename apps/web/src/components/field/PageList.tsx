import { FieldPage } from '../../types'

interface PageListProps {
  pages: FieldPage[]
  selectedPageId: string | null
  onPageSelect: (page: FieldPage) => void
}

export function PageList({ pages, selectedPageId, onPageSelect }: PageListProps) {
  if (pages.length === 0) {
    return (
      <div className="w-60 h-full bg-slate-900/50 border-r border-slate-700/50 flex items-center justify-center">
        <p className="text-sm text-slate-500">Results will appear here</p>
      </div>
    )
  }

  return (
    <div className="w-60 h-full bg-slate-900/50 border-r border-slate-700/50 overflow-y-auto py-2">
      {pages.map((page) => {
        const isActive = page.id === selectedPageId

        return (
          <button
            key={page.id}
            onClick={() => onPageSelect(page)}
            className={`
              w-full p-2 text-left transition-colors
              ${
                isActive
                  ? 'bg-blue-500/20 border-l-2 border-blue-500'
                  : 'hover:bg-white/5 border-l-2 border-transparent'
              }
            `}
          >
            <div className="flex flex-col gap-1">
              <div className="aspect-[4/3] w-full bg-slate-800 rounded overflow-hidden mb-1">
                <img
                  src={page.pngDataUrl}
                  alt={page.title}
                  className="w-full h-full object-cover"
                />
              </div>
              <p className="text-sm font-medium text-white truncate">
                {page.title}
              </p>
              <p className="text-xs text-slate-400 line-clamp-2">
                {page.intro}
              </p>
              <p className="text-xs text-slate-500">
                {page.pointers.length} {page.pointers.length === 1 ? 'location' : 'locations'}
              </p>
            </div>
          </button>
        )
      })}
    </div>
  )
}
