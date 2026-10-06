// Routes: the six pages inside the AppShell, each loaded on demand; unknown paths go to the overview.
import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { AppShell } from './components/layout/AppShell'

const OverviewPage = lazy(() => import('./pages/OverviewPage').then((m) => ({ default: m.OverviewPage })))
const MapPage = lazy(() => import('./pages/MapPage').then((m) => ({ default: m.MapPage })))
const PayPage = lazy(() => import('./pages/PayPage').then((m) => ({ default: m.PayPage })))
const JobsPage = lazy(() => import('./pages/JobsPage').then((m) => ({ default: m.JobsPage })))
const PostsPage = lazy(() => import('./pages/PostsPage').then((m) => ({ default: m.PostsPage })))
const GroupsPage = lazy(() => import('./pages/GroupsPage').then((m) => ({ default: m.GroupsPage })))

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="map" element={<MapPage />} />
        <Route path="pay" element={<PayPage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="posts" element={<PostsPage />} />
        <Route path="groups" element={<GroupsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
