import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TopBar from './components/TopBar';
import { CustomerProvider } from './customer';
import Dashboard from './pages/Dashboard';
import UploadBatch from './pages/UploadBatch';
import AuditTrail from './pages/AuditTrail';
import ReviewQueue from './pages/ReviewQueue';
import CaseReview from './pages/CaseReview';

const queryClient = new QueryClient();

const tabs = [
  { path: "/", label: "Dashboard" },
  { path: "/upload", label: "Upload & Match" },
  { path: "/review", label: "Review Queue" },
  { path: "/audit", label: "Audit Trail" },
];

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <CustomerProvider>
      <BrowserRouter>
        <div className="min-h-screen flex flex-col">
          <TopBar />

          <nav className="flex gap-[2px] px-3 pt-2 border-b border-border bg-bg">
            {tabs.map((tab) => (
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

          <main className="flex-1 bg-bg">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/upload" element={<UploadBatch />} />
              <Route path="/review" element={<ReviewQueue />} />
              <Route path="/case/:runId" element={<CaseReview />} />
              <Route path="/audit" element={<AuditTrail />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
      </CustomerProvider>
    </QueryClientProvider>
  );
}
