import { createBrowserRouter } from 'react-router'

import { RequireAuth } from './auth/RequireAuth'
import { Layout } from './components/Layout'
import { EditorPage } from './pages/EditorPage'
import { EventPage } from './pages/EventPage'
import { GroupPage } from './pages/GroupPage'
import { HomePage } from './pages/HomePage'
import { JoinPage } from './pages/JoinPage'
import { LivePage } from './pages/LivePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProfilePage } from './pages/ProfilePage'
import { WatchPage } from './pages/WatchPage'

const signedIn = (element: React.ReactNode) => <RequireAuth>{element}</RequireAuth>

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'profile', element: signedIn(<ProfilePage />) },
      { path: 'groups/:groupId', element: signedIn(<GroupPage />) },
      { path: 'events/:eventId', element: signedIn(<EventPage />) },
      { path: 'events/:eventId/questions', element: signedIn(<EditorPage />) },
      { path: 'events/:eventId/play', element: signedIn(<LivePage />) },
      // Open to anyone with the link; they sign in from there.
      { path: 'join/:code', element: <JoinPage /> },
      { path: 'watch/:token', element: <WatchPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
