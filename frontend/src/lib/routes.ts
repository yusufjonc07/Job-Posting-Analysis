// The six pages: path, nav label, icon and the title/subtitle shown in the top bar.
import { Briefcase, FileText, LayoutDashboard, Map, Users, Wallet, type LucideIcon } from 'lucide-react'

export interface PageRoute {
  path: string
  label: string
  title: string
  subtitle: string
  icon: LucideIcon
}

export const ROUTES: PageRoute[] = [
  {
    path: '/',
    label: 'Overview',
    title: 'Overview',
    subtitle: 'Job ads posted in Uzbek-language Telegram groups in Korea, updated live as the crawler runs',
    icon: LayoutDashboard,
  },
  {
    path: '/map',
    label: 'Map',
    title: 'Where the jobs are',
    subtitle: 'Unique job ads per province — click a region for details',
    icon: Map,
  },
  {
    path: '/pay',
    label: 'Pay',
    title: 'Pay',
    subtitle: 'Salaries stated in ads, by pay period',
    icon: Wallet,
  },
  {
    path: '/jobs',
    label: 'Jobs & visas',
    title: 'Jobs & visas',
    subtitle: 'Occupations and visa types named in ads',
    icon: Briefcase,
  },
  {
    path: '/posts',
    label: 'Posts',
    title: 'Posts',
    subtitle: 'How ads are written: script, contact details, length and reposts',
    icon: FileText,
  },
  {
    path: '/groups',
    label: 'Groups',
    title: 'Telegram groups',
    subtitle: 'The groups the ads come from',
    icon: Users,
  },
]

export function routeFor(pathname: string): PageRoute {
  return ROUTES.find((r) => r.path === pathname) ?? ROUTES[0]
}
