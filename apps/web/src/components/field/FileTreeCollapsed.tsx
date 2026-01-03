import { DisciplineInHierarchy } from '../../types'

interface FileTreeCollapsedProps {
  disciplines: DisciplineInHierarchy[]
  selectedDisciplineId: string | null
  onDisciplineSelect: (disciplineId: string) => void
}

const DISCIPLINE_ABBREVIATIONS: Record<string, string> = {
  architectural: 'A',
  structural: 'S',
  mep: 'MEP',
  civil: 'C',
  kitchen: 'K',
  vapor_mitigation: 'VM',
  canopy: 'CN',
  unknown: '?',
}

export function FileTreeCollapsed({
  disciplines,
  selectedDisciplineId,
  onDisciplineSelect,
}: FileTreeCollapsedProps) {
  return (
    <div className="w-16 h-full flex flex-col items-center gap-2 py-4">
      {disciplines.map((discipline) => {
        const abbreviation =
          DISCIPLINE_ABBREVIATIONS[discipline.name] ||
          discipline.name.slice(0, 2).toUpperCase()
        const isActive = discipline.id === selectedDisciplineId

        return (
          <button
            key={discipline.id}
            onClick={() => onDisciplineSelect(discipline.id)}
            title={discipline.displayName}
            className={`
              w-12 h-12 rounded-lg flex items-center justify-center
              text-sm font-medium transition-colors
              ${
                isActive
                  ? 'bg-blue-500/20 ring-2 ring-blue-500 text-white'
                  : 'bg-white/5 text-slate-300 hover:bg-white/10'
              }
            `}
          >
            {abbreviation}
          </button>
        )
      })}
    </div>
  )
}
