import '@fontsource/barlow/400.css'
import '@fontsource/barlow/500.css'
import '@fontsource/barlow-semi-condensed/500.css'
import '@fontsource/barlow-semi-condensed/600.css'
import './styles.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, HomeRoute, RequireAuth } from './auth'
import { FieldPage } from './field/FieldPage'
import { EvaluationPage } from './pages/EvaluationPage'
import { Layout } from './pages/Layout'
import { LoginPage } from './pages/LoginPage'
import { MissionPage } from './pages/MissionPage'
import { MissionsPage } from './pages/MissionsPage'
import { NewMissionPage } from './pages/NewMissionPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/field/:id?"
            element={
              <RequireAuth>
                <FieldPage />
              </RequireAuth>
            }
          />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<HomeRoute missions={<MissionsPage />} />} />
            <Route path="missions/new" element={<NewMissionPage />} />
            <Route path="missions/:id" element={<MissionPage />} />
            <Route path="evaluation" element={<EvaluationPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)

// Installable field view (PWA). The worker is network-first and never caches live data.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  })
}
