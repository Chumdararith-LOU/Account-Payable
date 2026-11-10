import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TopBar from './components/TopBar';
import { CustomerProvider } from './customer';
import { AuthProvider, useAuth } from './auth';
import Dashboard from './pages/Dashboard';
import UploadBatch from './pages/UploadBatch';
import AuditTrail from './pages/AuditTrail';
import ReviewQueue from './pages/ReviewQueue';
import CaseReview from './pages/CaseReview';
import SignIn from './pages/SignIn';
import ChangePassword from './pages/ChangePassword';
import Users from './pages/Users';

const queryClient = new QueryClient();

const tabs = [
  { path: "/", label: "Dashboard" },
  { path: "/upload", label: "Upload & Match" },
  { path: "/review", label: "Review Queue" },
  { path: "/audit", label: "Audit Trail" },
];

function Shell() {
  const { user, loading } = useAuth();

  if (loading) return <div className="p-4">Loading…</div>;
  if (!user) return <SignIn />;

  const visibleTabs = user.role === 'admin' ? [...tabs, { path: '/users', label: 'Users' }] : tabs;

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />

      {!user.must_change_password && (
        <nav className="flex gap-[2px] px-3 pt-2 border-b border-border bg-bg">
          {visibleTabs.map((tab) => (
            <NavLink
              key={tab.path}
              to={tab.path}
              className={({ isActive }) =>
                `px-4 py-1.5 border border-b-0 rounded-t-[5px] font-bold text-[12px] transition-colors
                 ${isActive
                   ? 'bg-white border-border border-b-white text-[#222] relative top-[1px]'
                   : 'bg-win7-panel border-border text-gray-600 hover:bg-gray-200'}`
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}

      <main className="flex-1 bg-bg">
        {user.must_change_password ? (
          <ChangePassword forced />
        ) : (
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<UploadBatch />} />
            <Route path="/review" element={<ReviewQueue />} />
            <Route path="/case/:runId" element={<CaseReview />} />
            <Route path="/audit" element={<AuditTrail />} />
            <Route path="/account" element={<ChangePassword />} />
            <Route path="/users" element={user.role === 'admin' ? <Users /> : <Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <CustomerProvider>
          <BrowserRouter>
            <Shell />
          </BrowserRouter>
        </CustomerProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
