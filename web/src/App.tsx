import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, Outlet, RouterProvider, useLocation } from 'react-router'
import { Spinner } from './components/ui'
import { useMe } from './lib/queries'
import { AccountPage } from './pages/AccountPage'
import { BackupsPage } from './pages/BackupsPage'
import { GamesPage } from './pages/GamesPage'
import { InvitePage } from './pages/InvitePage'
import { LoginPage } from './pages/LoginPage'
import { PeoplePage } from './pages/PeoplePage'
import { ResetPage } from './pages/ResetPage'
import { TrashPage } from './pages/TrashPage'
import { ChaptersPage } from './pages/workspace/ChaptersPage'
import { ItemsPage } from './pages/workspace/ItemsPage'
import { ReferencePage } from './pages/workspace/ReferencePage'
import { RulesPage } from './pages/workspace/RulesPage'
import { SceneEditorPage } from './pages/workspace/SceneEditor'
import { SettingsPage } from './pages/workspace/SettingsPage'
import { VariablesPage } from './pages/workspace/VariablesPage'
import { Workspace, WorkspaceHome } from './pages/workspace/Workspace'

const GraphPage = lazy(() => import('./pages/workspace/GraphPage').then((m) => ({ default: m.GraphPage })))

function Loading({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <Spinner />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

function RequireAuth() {
  const me = useMe()
  const location = useLocation()
  if (me.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (!me.data?.authenticated) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return <Outlet />
}

/** Pages only the dashboard's owner can use (the server refuses everyone else anyway). */
function RequireOwner() {
  const me = useMe()
  return me.data?.user?.owner ? <Outlet /> : <Navigate to="/" replace />
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/invite/:token', element: <InvitePage /> },
  { path: '/reset/:token', element: <ResetPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: '/', element: <GamesPage /> },
      { path: '/account', element: <AccountPage /> },
      {
        element: <RequireOwner />,
        children: [
          { path: '/trash', element: <TrashPage /> },
          { path: '/backups', element: <BackupsPage /> },
          { path: '/people', element: <PeoplePage /> },
        ],
      },
      {
        path: '/games/:gameId',
        element: <Workspace />,
        children: [
          { index: true, element: <WorkspaceHome /> },
          { path: 'scenes/:pk', element: <SceneEditorPage /> },
          { path: 'graph', element: <Loading><GraphPage /></Loading> },
          { path: 'variables', element: <VariablesPage /> },
          { path: 'items', element: <ItemsPage /> },
          { path: 'rules', element: <RulesPage /> },
          { path: 'chapters', element: <ChaptersPage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: 'reference', element: <ReferencePage /> },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

export function App() {
  return <RouterProvider router={router} />
}
