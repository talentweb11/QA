import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';

// Auth pages (Daffa — FR-01/02/04/05/12/14)
import Login from './pages/Login';
import Register from './pages/Register';
import VerifyEmail from './pages/VerifyEmail';
import PasswordResetRequest from './pages/PasswordResetRequest';
import PasswordResetConfirm from './pages/PasswordResetConfirm';
import AcceptInvite from './pages/AcceptInvite';
import Profile from './pages/user/Profile';

// Other pages
import Unauthorized from './pages/Unauthorized';
import NotFound from './pages/NotFound';
import Dashboard from './pages/user/Dashboard';
import Upload from './pages/user/Upload';
import Transactions from './pages/user/Transactions';
import Categories from './pages/user/Categories';
import HouseholdSharing from './pages/user/HouseholdSharing';
import AdvisorSharing from './pages/user/AdvisorSharing';
import HouseholdSummary from './pages/household/HouseholdSummary';
import ClientList from './pages/advisor/ClientList';
import UserManagement from './pages/admin/UserManagement';
import AuditLogs from './pages/admin/AuditLogs';

// Redirects to /login when the session-expired flag is set by AuthContext
function SessionTimeoutRedirect() {
  const { sessionExpired } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (sessionExpired) {
      navigate('/login', { replace: true });
    }
  }, [sessionExpired, navigate]);

  return null;
}

function AppRoutes() {
  return (
    <>
      <SessionTimeoutRedirect />
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/password-reset" element={<PasswordResetRequest />} />
        <Route path="/password-reset/confirm" element={<PasswordResetConfirm />} />
        <Route path="/accept-invite" element={<AcceptInvite />} />
        <Route path="/unauthorized" element={<Unauthorized />} />
        <Route path="/404" element={<NotFound />} />

        {/* Protected routes inside the app shell */}
        <Route element={<Layout />}>
          {/* Any authenticated user */}
          <Route element={<ProtectedRoute />}>
            <Route path="/profile" element={<Profile />} />
          </Route>

          {/* INDIVIDUAL users */}
          <Route element={<ProtectedRoute allowedRoles={['INDIVIDUAL']} />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/categories" element={<Categories />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/sharing" element={<HouseholdSharing />} />
            <Route path="/advisor-access" element={<AdvisorSharing />} />
          </Route>

          {/* HOUSEHOLD users */}
          <Route element={<ProtectedRoute allowedRoles={['HOUSEHOLD']} />}>
            <Route path="/household" element={<HouseholdSummary />} />
          </Route>

          {/* ADVISOR users */}
          <Route element={<ProtectedRoute allowedRoles={['ADVISOR']} />}>
            <Route path="/advisor/clients" element={<ClientList />} />
          </Route>

          {/* ADMIN users */}
          <Route element={<ProtectedRoute allowedRoles={['ADMIN']} />}>
            <Route path="/admin/users" element={<UserManagement />} />
            <Route path="/admin/audit-logs" element={<AuditLogs />} />
          </Route>

          {/* Root redirect based on role */}
          <Route path="/" element={<RoleRedirect />} />
        </Route>

        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </>
  );
}

function RoleRedirect() {
  const { user, isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.roles.includes('ADMIN')) return <Navigate to="/admin/users" replace />;
  if (user?.roles.includes('ADVISOR')) return <Navigate to="/advisor/clients" replace />;
  if (user?.roles.includes('INDIVIDUAL')) return <Navigate to="/dashboard" replace />;
  if (user?.roles.includes('HOUSEHOLD')) return <Navigate to="/household" replace />;
  return <Navigate to="/dashboard" replace />;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
