import { initials } from '../lib/format'

// A fixed palette, picked by hashing the name, so a person keeps the same
// colour everywhere they appear (card, member list, comment).
const COLORS = ['bg-indigo-500', 'bg-emerald-500', 'bg-amber-500', 'bg-rose-500', 'bg-sky-500', 'bg-violet-500']

function colorFor(name: string): string {
  let hash = 0
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return COLORS[hash % COLORS.length]
}

export function Avatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' }) {
  const dimensions = size === 'sm' ? 'h-5 w-5 text-[9px]' : 'h-8 w-8 text-xs'
  return (
    <span
      title={name}
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white ${dimensions} ${colorFor(name)}`}
    >
      {initials(name)}
    </span>
  )
}
