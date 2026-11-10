import React from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

export default function Dashboard() {
  // Example of how you will fetch real data:
  // const { data, isLoading } = useQuery({
  //   queryKey: ['kpis'],
  //   queryFn: () => api.get('/kpis/routes').then(res => res.data)
  // });

  const kpis = [
    { label: "Auto-Approve Rate", value: "42%", color: "text-success", sub: "▲ 3.1% vs last week" },
    { label: "Review Queue", value: "18", color: "text-warning", sub: "items awaiting a clerk" },
    { label: "Docs Processed Today", value: "1,247", color: "text-navy-light", sub: "across all suppliers" },
    { label: "Avg. Processing Time", value: "1.8s", color: "text-navy-light", sub: "per document" },
  ];

  return (
    <div className="p-4">
      <div className="grid grid-cols-4 gap-3">
        {kpis.map((kpi, idx) => (
          <div key={idx} className="panel rounded-[9px] p-3 bg-[linear-gradient(rgba(255,255,255,0.35)_50%,rgba(0,0,0,0.02)_50%)] shadow-retro-btn">
            <span className="text-gray-600 block mb-1">{kpi.label}</span>
            <b className={`block text-3xl leading-tight ${kpi.color}`}>{kpi.value}</b>
            <span className="text-[11px] text-gray-500 mt-2 block">{kpi.sub}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-3 mt-4">
        <div className="col-span-2 panel">
          <div className="panel-header">Document Volume Trend – Last 14 Days</div>
          <div className="p-4 h-64 flex items-center justify-center text-gray-400 border-dashed border-2 m-2 bg-gray-50">
            [ Recharts Graph Component Will Go Here ]
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">Top Exception Codes</div>
          <div className="p-3">
            {[
              { code: 'LINE_AMOUNT_MISMATCH', pct: 38 },
              { code: 'PO_NOT_FOUND', pct: 27 },
              { code: 'DUPLICATE_INVOICE', pct: 19 },
              { code: 'TAX_CODE_INVALID', pct: 11 },
            ].map(ex => (
              <div key={ex.code} className="mb-3">
                <div className="flex justify-between mb-1">
                  <span className="font-mono text-[11px]">{ex.code}</span>
                  <b>{ex.pct}%</b>
                </div>
                <div className="h-3 bg-white border border-border overflow-hidden rounded-full">
                  <div className="h-full bg-warning" style={{ width: `${ex.pct}%` }}></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
