import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import DevStack from './components/DevStack'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import Admin from './pages/Admin'
import AgentMonitoring from './pages/AgentMonitoring'
import Agents from './pages/Agents'
import Analytics from './pages/Analytics'
import CampaignDetail from './pages/CampaignDetail'
import Campaigns from './pages/Campaigns'
import Companies from './pages/Companies'
import CompanyDetail from './pages/CompanyDetail'
import Crm from './pages/Crm'
import Dashboard from './pages/Dashboard'
import JobDetail from './pages/JobDetail'
import Jobs from './pages/Jobs'
import Login from './pages/Login'
import NotFound from './pages/NotFound'
import Prospects from './pages/Prospects'
import Register from './pages/Register'
import Reports from './pages/Reports'
import SettingsPage from './pages/Settings'
import { useAuth } from './store/auth'
import { useTheme } from './store/theme'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 20_000,
    },
  },
})

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'idle' || status === 'loading') {
    return <Loading label="Restoring your session…" />
  }
  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

function Bootstrap({ children }: { children: React.ReactNode }) {
  const bootstrap = useAuth((state) => state.bootstrap)
  const initTheme = useTheme((state) => state.init)

  useEffect(() => {
    initTheme()
    void bootstrap()
  }, [bootstrap, initTheme])

  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DevStack>
        <BrowserRouter>
          <Bootstrap>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route
                element={
                  <RequireAuth>
                    <Layout />
                  </RequireAuth>
                }
              >
                <Route index element={<Dashboard />} />
                <Route path="campaigns" element={<Campaigns />} />
                <Route path="campaigns/:id" element={<CampaignDetail />} />
                <Route path="jobs" element={<Jobs />} />
                <Route path="jobs/:id" element={<JobDetail />} />
                <Route path="agents" element={<Agents />} />
                <Route path="monitoring" element={<AgentMonitoring />} />
                <Route path="companies" element={<Companies />} />
                <Route path="companies/:id" element={<CompanyDetail />} />
                <Route path="prospects" element={<Prospects />} />
                <Route path="reports" element={<Reports />} />
                <Route path="crm" element={<Crm />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="admin" element={<Admin />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Bootstrap>
        </BrowserRouter>
      </DevStack>
    </QueryClientProvider>
  )
}
