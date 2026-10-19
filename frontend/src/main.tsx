import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import Layout from './components/Layout'
import Builder from './pages/Builder'
import JoinRoom from './pages/JoinRoom'
import Landing from './pages/Landing'
import NotFound from './pages/NotFound'
import OrganizerRoom from './pages/OrganizerRoom'
import Results from './pages/Results'

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <Landing /> },
      { path: '/build', element: <Builder /> },
      { path: '/join/:slug', element: <JoinRoom /> },
      { path: '/room/:slug', element: <OrganizerRoom /> },
      { path: '/plan/:id', element: <Results /> },
      { path: '/example/:id', element: <Results example /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
