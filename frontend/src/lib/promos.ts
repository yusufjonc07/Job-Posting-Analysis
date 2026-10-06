// Slides of the Overview carousel: sponsored placements and news. Sample content for now; later a backend
// (e.g. GET /api/promos) can serve the same shape, so only usePromos() has to change.
import { BadgeCheck, Building2, Filter, Lock, Megaphone, Radio, type LucideIcon } from 'lucide-react'

export type PromoKind = 'ad' | 'news'
export type PromoTone = 'blue' | 'indigo' | 'emerald' | 'amber'

export interface Promo {
  id: string
  kind: PromoKind
  title: string
  body: string
  /** Who pays for a sponsored slide (shown as "Sponsored · <sponsor>"). */
  sponsor?: string
  cta?: { label: string; href: string }
  tone: PromoTone
  icon: LucideIcon
}

/** Where "Advertise here" leads until there is an ads backend. */
export const ADVERTISE_URL = 'https://t.me/ishbor_kr_bot'

export function samplePromos({ groups }: { groups: number | null }): Promo[] {
  return [
    {
      id: 'advertise',
      kind: 'ad',
      title: 'Reach job seekers across Korea',
      body: "Put your vacancy or service in front of thousands of Uzbek-speaking workers who check Ish e'lonlari every day.",
      sponsor: "Ish e'lonlari · Korea",
      cta: { label: 'Advertise here', href: ADVERTISE_URL },
      tone: 'blue',
      icon: Megaphone,
    },
    {
      id: 'news-live-groups',
      kind: 'news',
      title: groups ? `${groups} Telegram groups followed live` : 'Telegram groups followed live',
      body: 'New job posts appear here seconds after they are posted, and new job groups are found from the links in posts.',
      cta: { label: 'See the latest ads', href: '/posts' },
      tone: 'emerald',
      icon: Radio,
    },
    {
      id: 'business-slot',
      kind: 'ad',
      title: 'Your company here',
      body: 'Factories, agencies, translators, money transfer, shipping: a sponsored card like this one is shown on the overview of every visitor.',
      sponsor: 'Sample placement',
      cta: { label: 'Book this spot', href: ADVERTISE_URL },
      tone: 'indigo',
      icon: Building2,
    },
    {
      id: 'news-job-filter',
      kind: 'news',
      title: 'Only real job offers are counted',
      body: 'Chat, questions, parcels, flights and sales are filtered out of every number. See what was left out on the Posts page.',
      cta: { label: 'What is filtered', href: '/posts' },
      tone: 'amber',
      icon: Filter,
    },
    {
      id: 'news-login',
      kind: 'news',
      title: 'Log in with Telegram',
      body: 'The Telegram groups behind every ad, with their activity and home province, are shown after logging in with your Telegram account.',
      cta: { label: 'See the groups', href: '/groups' },
      tone: 'indigo',
      icon: Lock,
    },
    {
      id: 'verified-employers',
      kind: 'ad',
      title: 'Verified employer badge',
      body: 'Coming soon: employers can verify their company and get a badge on every ad they post.',
      sponsor: 'Sample placement',
      tone: 'emerald',
      icon: BadgeCheck,
    },
  ]
}
