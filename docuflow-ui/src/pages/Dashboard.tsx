import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import api from '../api/client';
import { reasonLabel, type CodeCount, type RecentRun, type RouteCounts } from '../api/types';
import RouteChip from '../components/RouteChip';
import { useCustomer } from '../customer';

export default function Dashboard() {
  const { customer } = useCustomer();
  const params = { customer_id: customer };

  const { data: counts } = useQuery<RouteCounts>({
    queryKey: ['caseCounts', customer],
    queryFn: () => api.get('/kpis/cases', { params }).then((res) => res.data),
    refetchInterval: 10000,
  });
  const { data: codes } = useQuery<CodeCount[]>({
    queryKey: ['failureCodes', customer],
    queryFn: () => api.get('/kpis/failure-codes', { params: { ...params, limit: 6 } }).then((res) => res.data),
    refetchInterval: 10000,
  });
  const { data: recent } = useQuery<RecentRun[]>({
    queryKey: ['recentRuns', customer, 12],
    queryFn: () => api.get('/kpis/recent', { params: { ...params, limit: 12 } }).then((res) => res.data),
    refetchInterval: 10000,
  });

  const total = counts?.total ?? 0;
  const pct = (n: number) => (total ? `${Math.round((n / total) * 100)}%` : '–');
  const kpis = [
    { label: 'Auto-Approve Rate', value: pct(counts?.auto_approve ?? 0), color: 'text-success', sub: `${counts?.auto_approve ?? 0} ${(counts?.auto_approve ?? 0) === 1 ? 'case' : 'cases'} approved with no human touch` },
    { label: 'Review Queue', value: String(counts?.human_review ?? 0), color: 'text-warning', sub: 'cases awaiting a clerk' },
    { label: 'Rejected', value: String(counts?.reject ?? 0), color: 'text-danger', sub: 'will not be paid' },
    { label: 'Cases Processed', value: total.toLocaleString(), color: 'text-navy-light', sub: `for customer "${customer}"` },
  ];
  const codeTotal = (codes ?? []).reduce((s, c) => s + c.count, 0);

  return (
    <div className="p-4">
      <div className="grid grid-cols-4 gap-3">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="panel rounded-[9px] p-3 bg-[linear-gradient(rgba(255,255,255,0.35)_50%,rgba(0,0,0,0.02)_50%)] shadow-retro-btn">
            <span className="text-gray-600 block mb-1">{kpi.label}</span>
            <b className={`block text-3xl leading-tight ${kpi.color}`}>{kpi.value}</b>
            <span className="text-[11px] text-gray-500 mt-2 block">{kpi.sub}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-3 mt-4">
        <div className="col-span-2 panel">
          <div className="panel-header">Recent Cases</div>
          <table className="w-full text-left border-collapse bg-white">
            <thead className="bg-win7-panel border-b border-gray-300">
              <tr>
                <th className="p-2 border-r border-gray-300">Invoice #</th>
                <th className="p-2 border-r border-gray-300">Decision</th>
                <th className="p-2 border-r border-gray-300">Reason</th>
                <th className="p-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {(recent ?? []).length === 0 ? (
                <tr><td colSpan={4} className="p-4 text-center text-gray-400">No documents processed yet for this customer.</td></tr>
              ) : (
                recent!.map((r) => (
                  <tr key={r.run_id} className="border-b border-gray-200 hover:bg-blue-50">
                    <td className="p-2 font-bold">
                      <Link to={`/case/${r.run_id}`} className="text-blue-600 hover:underline">{r.invoice_number || 'N/A'}</Link>
                    </td>
                    <td className="p-2"><RouteChip route={r.route} /></td>
                    <td className="p-2">{reasonLabel(r.route_reason)}</td>
                    <td className="p-2 text-gray-500 text-[11px]">{new Date(r.run_timestamp).toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <div className="panel-header">Top Exception Codes</div>
          <div className="p-3">
            {(codes ?? []).length === 0 && <div className="text-gray-400">No exceptions yet.</div>}
            {(codes ?? []).map((ex) => {
              const p = codeTotal ? Math.round((ex.count / codeTotal) * 100) : 0;
              return (
                <div key={ex.code} className="mb-3">
                  <div className="flex justify-between mb-1">
                    <span className="font-mono text-[11px]">{ex.code}</span>
                    <b>{p}%</b>
                  </div>
                  <div className="h-3 bg-white border border-border overflow-hidden rounded-full">
                    <div className="h-full bg-warning" style={{ width: `${p}%` }}></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
