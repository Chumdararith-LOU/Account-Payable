import { useQuery } from '@tanstack/react-query';
import { Building2, Plus } from 'lucide-react';
import api from '../api/client';
import { CUSTOMER_ID_RE, useCustomer } from '../customer';

export default function TopBar() {
  const { customer, setCustomer } = useCustomer();
  const { data: customers } = useQuery<string[]>({
    queryKey: ['customers'],
    queryFn: () => api.get('/customers').then((res) => res.data),
  });
  const options = Array.from(new Set(['default', customer, ...(customers ?? [])])).sort();

  const addCustomer = () => {
    const id = window.prompt('New customer ID (lowercase letters, digits, - or _):', '');
    if (id === null) return;
    const clean = id.trim().toLowerCase();
    if (!CUSTOMER_ID_RE.test(clean)) {
      window.alert('Use only lowercase letters, digits, "-" or "_" (max 64).');
      return;
    }
    setCustomer(clean);
  };

  return (
    <header className="bg-win7 border-b-[3px] border-navy-dark text-white flex justify-between items-center p-2 px-4 shadow-md">
      <div className="flex flex-col">
        <h1 className="text-2xl font-bold tracking-tight text-white drop-shadow-[1px_1px_0_#000]">
          DocuFlow<span className="text-[#9fd0ff]">AP</span>
        </h1>
        <span className="text-[11px] opacity-85">Accounts Payable Document Intelligence</span>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 bg-black/30 border border-navy-dark px-2 py-1 rounded-[4px] shadow-inner">
          <Building2 size={14} className="text-gray-300" />
          <label htmlFor="customer" className="font-bold text-[11px] uppercase tracking-wider text-gray-200">Customer:</label>
          <select
            id="customer"
            value={customer}
            onChange={(e) => setCustomer(e.target.value)}
            className="bg-[#cfd9e4] text-navy-dark font-bold text-[13px] px-1 py-0.5 border border-navy-dark rounded-[3px] outline-none"
          >
            {options.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <button onClick={addCustomer} title="Add a customer" aria-label="Add a customer" className="text-gray-300 hover:text-white transition-colors">
            <Plus size={16} />
          </button>
        </div>
      </div>
    </header>
  );
}
