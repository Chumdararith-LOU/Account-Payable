import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import { X, ShieldAlert, CheckCircle2 } from 'lucide-react';

export default function AuditTrail() {
  const [selectedRun, setSelectedRun] = useState<string | null>(null);

  // Fetch recent runs for the table
  const { data: recentRuns, isLoading } = useQuery({
    queryKey: ['recentRuns'],
    queryFn: () => api.get('/kpis/recent?limit=50').then(res => res.data),
    refetchInterval: 5000, // Auto-refresh every 5s
  });

  // Fetch full details for the selected run
  const { data: runDetails, isLoading: isLoadingDetails } = useQuery({
    queryKey: ['runDetails', selectedRun],
    queryFn: () => api.get(`/audit/${selectedRun}`).then(res => res.data),
    enabled: !!selectedRun,
  });

  const getRouteStyle = (route: string) => {
    if (route === 'AUTO_APPROVE') return 'bg-green-100 text-green-800 border-green-300';
    if (route === 'HUMAN_REVIEW') return 'bg-orange-100 text-orange-800 border-orange-300';
    if (route === 'REJECT') return 'bg-red-100 text-red-800 border-red-300';
    return 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="p-4">
      <div className="panel">
        <div className="panel-header flex justify-between items-center">
          <span>Audit Trail – Document Explorer</span>
          <span className="text-gray-500 text-[11px] font-normal">Click a row to view decision details</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse bg-white">
            <thead className="bg-win7-panel border-b border-gray-300">
              <tr>
                <th className="p-2 border-r border-gray-300 font-bold">Run ID</th>
                <th className="p-2 border-r border-gray-300 font-bold">Invoice #</th>
                <th className="p-2 border-r border-gray-300 font-bold">Route</th>
                <th className="p-2 border-r border-gray-300 font-bold">Confidence</th>
                <th className="p-2 border-r border-gray-300 font-bold">Reason</th>
                <th className="p-2 font-bold">Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={6} className="p-4 text-center">Loading...</td></tr>
              ) : recentRuns?.map((run: any) => (
                <tr
                  key={run.run_id}
                  onClick={() => setSelectedRun(run.run_id)}
                  className="border-b border-gray-200 hover:bg-blue-50 cursor-pointer transition-colors"
                >
                  <td className="p-2 font-mono text-[11px] text-blue-600 truncate max-w-[120px]">{run.run_id}</td>
                  <td className="p-2 font-bold">{run.invoice_number || 'N/A'}</td>
                  <td className="p-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getRouteStyle(run.route)}`}>
                      {run.route}
                    </span>
                  </td>
                  <td className="p-2">{(run.score * 100).toFixed(1)}%</td>
                  <td className="p-2 font-mono text-[11px]">{run.route_reason}</td>
                  <td className="p-2 text-gray-500 text-[11px]">{new Date(run.run_timestamp).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Drawer Overlay */}
      {selectedRun && (
        <div className="fixed inset-0 bg-black/30 z-40" onClick={() => setSelectedRun(null)}>
          <div
            className="absolute top-0 right-0 bottom-0 w-[450px] bg-panel border-l-2 border-navy shadow-2xl flex flex-col transform transition-transform"
            onClick={e => e.stopPropagation()} // Prevent close when clicking inside
          >
            <div className="bg-win7 text-white p-3 flex justify-between items-center">
              <h3 className="font-bold flex items-center gap-2">
                <ShieldAlert size={16} /> Decision Detail
              </h3>
              <button onClick={() => setSelectedRun(null)} className="hover:text-gray-300">
                <X size={18} />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1">
              {isLoadingDetails ? (
                <div className="text-center py-10">Loading details...</div>
              ) : runDetails && (
                <>
                  <div className="mb-4">
                    <div className="text-[11px] text-gray-500 font-bold uppercase mb-1">Document</div>
                    <div className="font-mono text-lg font-bold text-navy">{runDetails.invoice_number}</div>
                    <div className="mt-2 text-[11px]">
                      <span className={`px-2 py-1 rounded border font-bold ${getRouteStyle(runDetails.route)}`}>
                        {runDetails.route}
                      </span>
                    </div>
                  </div>

                  <div className="mb-4">
                    <div className="text-[11px] text-gray-500 font-bold uppercase mb-1">Extraction Engine</div>
                    <div className="font-bold text-sm">
                      {runDetails.extraction_source === 'vlm' ? '🤖 Qwen2.5-VL' : '⚠️ Heuristic OCR (Fallback)'}
                    </div>
                  </div>

                  <div className="mb-6">
                    <div className="text-[11px] text-gray-500 font-bold uppercase mb-1">Input Hash (SHA-256)</div>
                    <div className="bg-gray-100 p-2 border border-gray-300 font-mono text-[10px] break-all text-gray-700">
                      {runDetails.input_hash}
                    </div>
                  </div>

                  <div className="mb-6">
                    <div className="text-[11px] text-gray-500 font-bold uppercase mb-2">Validation Failures</div>
                    {runDetails.validation_failures?.length > 0 ? (
                      <ul className="space-y-2">
                        {runDetails.validation_failures.map((f: any, i: number) => (
                          <li key={i} className="bg-red-50 border border-red-200 p-2 text-[11px]">
                            <b className="text-red-700">{f.code}</b> ({f.severity})<br/>
                            <span className="text-gray-600">Location: {f.location}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="text-green-600 flex items-center gap-1 text-[11px]"><CheckCircle2 size={14}/> No validation errors</div>
                    )}
                  </div>

                  <div className="mb-6">
                    <div className="text-[11px] text-gray-500 font-bold uppercase mb-2">Match Failures</div>
                    {runDetails.match_failures?.length > 0 ? (
                      <ul className="space-y-2">
                        {runDetails.match_failures.map((f: any, i: number) => (
                          <li key={i} className="bg-orange-50 border border-orange-200 p-2 text-[11px]">
                            <b className="text-orange-700">{f.code}</b> ({f.severity})<br/>
                            <span className="text-gray-600">Location: {f.location}</span><br/>
                            {f.expected && <span className="text-gray-600">Expected: {f.expected} | Actual: {f.actual}</span>}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="text-green-600 flex items-center gap-1 text-[11px]"><CheckCircle2 size={14}/> No match errors</div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
