import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, HomeRoute, RequireAuth } from './auth'
import { FieldPage } from './field/FieldPage'
import { DatabasePage } from './pages/DatabasePage'
import { EvaluationPage } from './pages/EvaluationPage'
import { HistoryPage } from './pages/HistoryPage'
import { Layout } from './pages/Layout'
import { LoginPage } from './pages/LoginPage'
import { MissionPage } from './pages/MissionPage'
import { MissionsPage } from './pages/MissionsPage'
import { NewMissionPage } from './pages/NewMissionPage'
import { SensorsPage } from './pages/SensorsPage'
import { PrefsProvider } from './prefs'

// three.js is large: the 3D view loads only when it is opened.
const View3DPage = lazy(() => import('./view3d/View3DPage'))

/** The whole app: sign-in, preferences and every page. main.tsx mounts it; the tests render it too. */
export function App() {
  return (
    <AuthProvider>
      <PrefsProvider>
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
              path="/missions/:id/3d"
              element={
                <RequireAuth>
                  <Suspense fallback={<main className="v3d v3d-empty"><p>Loading the 3D view…</p></main>}>
                    <View3DPage />
                  </Suspense>
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
              <Route path="history" element={<HistoryPage />} />
              <Route path="evaluation" element={<EvaluationPage />} />
              <Route path="sensors" element={<SensorsPage />} />
              <Route path="database" element={<DatabasePage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </PrefsProvider>
    </AuthProvider>
  )
}
