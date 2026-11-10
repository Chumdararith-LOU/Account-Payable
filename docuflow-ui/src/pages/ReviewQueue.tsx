import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ClipboardList } from 'lucide-react';
import api from '../api/client';
import { reasonLabel, type RecentRun } from '../api/types';
import { useCustomer } from '../customer';

function waitingFor(ts: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 60000));
  if (mins < 60) return `${mins} min`;
  const hours = Math.round(mins / 60);
  return hours < 48 ? `${hours} h` : `${Math.round(hours / 24)} days`;
}

export default function ReviewQueue() {
  const { customer } = useCustomer();
  const { data: queue, isLoading } = useQuery<RecentRun[]>({
    queryKey: ['reviewQueue', customer],
    queryFn: () => api.get('/review-queue', { params: { customer_id: customer } }).then((res) => res.data),
    refetchInterval: 10000,
  });

  return (
    <div className="p-4">
      <div className="panel">
        <div className="panel-header flex justify-between items-center">
          <span className="flex items-center gap-1"><ClipboardList size={14} /> Review Queue – {queue?.length ?? 0} case(s) waiting</span>
          <span className="text-gray-500 text-[11px] font-normal">Oldest first. Open a case to correct fields or decide.</span>
        </div>
        <table className="w-full text-left border-collapse bg-white">
          <thead className="bg-win7-panel border-b border-gray-300">
            <tr>
              <th className="p-2 border-r border-gray-300 font-bold">Invoice #</th>
              <th className="p-2 border-r border-gray-300 font-bold">Why it needs a person</th>
              <th className="p-2 border-r border-gray-300 font-bold">Details</th>
              <th className="p-2 border-r border-gray-300 font-bold">Waiting</th>
              <th className="p-2 font-bold"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="p-4 text-center">Loading...</td></tr>
            ) : (queue ?? []).length === 0 ? (
              <tr><td colSpan={5} className="p-6 text-center text-gray-500">Nothing to review for customer "{customer}". </td></tr>
            ) : (
              queue!.map((r) => (
                <tr key={r.run_id} className="border-b border-gray-200 hover:bg-blue-50">
                  <td className="p-2 font-bold font-mono">{r.invoice_number || 'N/A'}</td>
                  <td className="p-2">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold border bg-orange-100 text-orange-800 border-orange-300">
                      {reasonLabel(r.route_reason)}
                    </span>
                  </td>
                  <td className="p-2 text-[11px] text-gray-700 max-w-[420px] truncate" title={r.remark}>{r.remark}</td>
                  <td className="p-2 text-[11px] text-gray-500 whitespace-nowrap">{waitingFor(r.run_timestamp)}</td>
                  <td className="p-2 text-right">
                    <Link to={`/case/${r.run_id}`} className="btn inline-block no-underline">Open</Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
