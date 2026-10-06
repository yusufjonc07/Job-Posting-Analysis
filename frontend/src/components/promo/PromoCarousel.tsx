// Carousel of sponsored slides and news above the Overview header: auto-advances (paused on hover, focus and
// for reduced motion), with arrows, dots and keyboard support.
import clsx from 'clsx'
import { ArrowRight, ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useHealth } from '../../api/hooks'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useLinkTo } from '../../lib/links'
import { samplePromos, type Promo, type PromoTone } from '../../lib/promos'

const SLIDE_MS = 7000

const TONES: Record<PromoTone, { panel: string; icon: string; button: string }> = {
  blue: { panel: 'from-blue-500/15 via-sky-400/10 to-transparent', icon: 'bg-blue-600 text-white', button: 'bg-blue-600 hover:bg-blue-700' },
  indigo: { panel: 'from-indigo-500/15 via-violet-400/10 to-transparent', icon: 'bg-indigo-600 text-white', button: 'bg-indigo-600 hover:bg-indigo-700' },
  emerald: { panel: 'from-emerald-500/15 via-teal-400/10 to-transparent', icon: 'bg-emerald-600 text-white', button: 'bg-emerald-600 hover:bg-emerald-700' },
  amber: { panel: 'from-amber-400/20 via-orange-300/10 to-transparent', icon: 'bg-amber-500 text-white', button: 'bg-amber-600 hover:bg-amber-700' },
}

/** Slides to show; sample content until a backend serves sponsored slides and news. */
export function usePromos(): Promo[] {
  const health = useHealth()
  const groups = health.data?.listener?.groups
  const followed = groups ? groups.live + groups.polled : null
  return useMemo(() => samplePromos({ groups: followed }), [followed])
}

export function PromoCarousel({ className }: { className?: string }) {
  const promos = usePromos()
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)')
  const count = promos.length
  const go = (next: number) => setIndex(((next % count) + count) % count)

  useEffect(() => {
    if (paused || reducedMotion || count < 2) return
    const timer = window.setTimeout(() => setIndex((i) => (i + 1) % count), SLIDE_MS)
    return () => window.clearTimeout(timer)
  }, [index, paused, reducedMotion, count])

  if (!count) return null
  return (
    <section
      aria-roledescription="carousel"
      aria-label="Sponsored and news"
      className={clsx('glass relative overflow-hidden', className)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') go(index - 1)
        if (e.key === 'ArrowRight') go(index + 1)
      }}
    >
      <div className="flex transition-transform duration-500 ease-out motion-reduce:transition-none" style={{ transform: `translateX(-${index * 100}%)` }}>
        {promos.map((promo, i) => (
          <Slide key={promo.id} promo={promo} active={i === index} position={`${i + 1} of ${count}`} />
        ))}
      </div>

      {count > 1 && (
        <div className="absolute right-4 bottom-3 flex items-center gap-2">
          <div className="flex items-center gap-1.5" role="tablist" aria-label="Slides">
            {promos.map((promo, i) => (
              <button
                key={promo.id}
                type="button"
                role="tab"
                aria-selected={i === index}
                aria-label={`Slide ${i + 1}: ${promo.title}`}
                onClick={() => go(i)}
                className={clsx('h-1.5 rounded-full transition-all', i === index ? 'w-5 bg-slate-700' : 'w-1.5 bg-slate-400/60 hover:bg-slate-500')}
              />
            ))}
          </div>
          <button type="button" aria-label="Previous slide" onClick={() => go(index - 1)} className="rounded-lg p-1 text-slate-500 hover:bg-white/70 hover:text-slate-900">
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <button type="button" aria-label="Next slide" onClick={() => go(index + 1)} className="rounded-lg p-1 text-slate-500 hover:bg-white/70 hover:text-slate-900">
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
      )}
      {count > 1 && !paused && !reducedMotion && (
        <div key={index} className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-slate-900/15" style={{ animation: `promo-progress ${SLIDE_MS}ms linear both` }} />
      )}
    </section>
  )
}

function Slide({ promo, active, position }: { promo: Promo; active: boolean; position: string }) {
  const linkTo = useLinkTo()
  const tone = TONES[promo.tone]
  const Icon = promo.icon
  const external = promo.cta?.href.startsWith('http')
  const buttonClass = clsx(
    'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl px-4 text-[13px] font-medium text-white shadow-sm transition-colors',
    tone.button,
  )
  return (
    <div
      role="group"
      aria-roledescription="slide"
      aria-label={position}
      aria-hidden={!active}
      className={clsx('flex w-full shrink-0 flex-wrap items-center gap-x-5 gap-y-3 bg-gradient-to-r px-5 pt-4 pb-9', tone.panel)}
    >
      <span className={clsx('hidden size-12 shrink-0 items-center justify-center rounded-2xl shadow-sm sm:flex', tone.icon)}>
        <Icon className="size-6" aria-hidden />
      </span>
      <div className="min-w-0 basis-full md:basis-0 md:flex-1">
        <div className="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
          {promo.kind === 'ad' ? `Sponsored${promo.sponsor ? ` · ${promo.sponsor}` : ''}` : 'News'}
        </div>
        <h2 className="mt-0.5 text-[16px] leading-6 font-semibold text-slate-900">{promo.title}</h2>
        <p className="mt-0.5 line-clamp-2 max-w-3xl text-[13px] leading-5 text-slate-600">{promo.body}</p>
      </div>
      {promo.cta &&
        (external ? (
          <a href={promo.cta.href} target="_blank" rel="noreferrer sponsored" tabIndex={active ? 0 : -1} className={buttonClass}>
            {promo.cta.label}
            <ArrowRight className="size-3.5" aria-hidden />
          </a>
        ) : (
          <Link to={linkTo(promo.cta.href)} tabIndex={active ? 0 : -1} className={buttonClass}>
            {promo.cta.label}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        ))}
    </div>
  )
}
