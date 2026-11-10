import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, CheckCircle2, Lock, Plus, RefreshCw, Trash2, XCircle } from 'lucide-react';
import api from '../api/client';
import { reasonLabel, type AuditDetail, type Doc, type Documents, type Failure, type LineItem } from '../api/types';
import AuthImage from '../components/AuthImage';
import RouteChip from '../components/RouteChip';

type DocKey = 'invoice' | 'po' | 'grni' | 'pard';

const DOC_TABS: { key: DocKey; label: string }[] = [
  { key: 'invoice', label: 'Invoice' },
  { key: 'po', label: 'Purchase Order' },
  { key: 'grni', label: 'Goods Received' },
  { key: 'pard', label: 'Payment Advice' },
];

interface FieldDef {
  name: string;
  label: string;
  type?: 'date';
}

const HEADER_FIELDS: Record<DocKey, FieldDef[]> = {
  invoice: [
    { name: 'invoice_number', label: 'Invoice #' },
    { name: 'vendor_name', label: 'Vendor' },
    { name: 'vendor_tax_id', label: 'Vendor tax ID' },
    { name: 'invoice_date', label: 'Invoice date', type: 'date' },
    { name: 'currency', label: 'Currency' },
    { name: 'po_number', label: 'PO #' },
    { name: 'subtotal', label: 'Subtotal' },
    { name: 'discount_amount', label: 'Discount' },
    { name: 'tax_amount', label: 'Tax' },
    { name: 'total', label: 'Total' },
    { name: 'exchange_rate', label: 'KHR per USD' },
    { name: 'total_khr', label: 'Total in KHR' },
  ],
  po: [
    { name: 'po_number', label: 'PO #' },
    { name: 'vendor_name', label: 'Vendor' },
    { name: 'vendor_tax_id', label: 'Vendor tax ID' },
    { name: 'po_date', label: 'PO date', type: 'date' },
    { name: 'currency', label: 'Currency' },
    { name: 'total', label: 'Total' },
  ],
  grni: [
    { name: 'grn_number', label: 'GRN #' },
    { name: 'vendor_name', label: 'Vendor' },
    { name: 'grni_date', label: 'Received date', type: 'date' },
  ],
  pard: [
    { name: 'pard_number', label: 'Payment advice #' },
    { name: 'invoice_number', label: 'Invoice # paid' },
    { name: 'amount', label: 'Amount paid' },
    { name: 'payment_date', label: 'Payment date', type: 'date' },
    { name: 'currency', label: 'Currency' },
    { name: 'reference', label: 'Reference' },
  ],
};

const HAS_LINES: Record<DocKey, boolean> = { invoice: true, po: true, grni: true, pard: false };
const LINE_MONEY: Record<DocKey, boolean> = { invoice: true, po: true, grni: false, pard: false };

function cleanDocs(extracted: Documents | null): Record<DocKey, Doc | null> {
  const src = extracted ?? { invoice: null, po: null, grni: null, pard: null };
  const copy = (d: Doc | null) => (d ? (JSON.parse(JSON.stringify(d)) as Doc) : null);
  return { invoice: copy(src.invoice), po: copy(src.po), grni: copy(src.grni), pard: copy(src.pard) };
}

// The API expects null, not "", for a value that is not there.
function toPayload(docs: Record<DocKey, Doc | null>) {
  const out: Record<string, unknown> = {};
  (Object.keys(docs) as DocKey[]).forEach((k) => {
    const d = docs[k];
    if (!d) {
      out[k] = null;
      return;
    }
    const doc: Record<string, unknown> = {};
    Object.entries(d).forEach(([field, value]) => {
      doc[field] = typeof value === 'string' && value.trim() === '' ? null : value;
    });
    if (d.line_items) {
      doc.line_items = d.line_items.map((li, i) => {
        const line: Record<string, unknown> = { ...li, line_no: i + 1 };
        (['quantity', 'unit_price', 'amount'] as const).forEach((f) => {
          const v = line[f];
          if (typeof v === 'string' && v.trim() === '') line[f] = null;
        });
        return line;
      });
    }
    out[k] = doc;
  });
  return out;
}

function errorText(err: unknown): string {
  const e = err as { response?: { data?: { detail?: unknown; error_code?: string } } };
  const detail = e.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return 'Please fill in the note before deciding.';
  return 'The request failed. Is the server reachable?';
}

export default function CaseReview() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<DocKey>('invoice');
  const [draft, setDraft] = useState<Record<DocKey, Doc | null> | null>(null);
  const [note, setNote] = useState('');

  const { data, isLoading, isError } = useQuery<AuditDetail>({
    queryKey: ['audit', runId],
    queryFn: () => api.get(`/audit/${runId}`).then((res) => res.data),
  });

  useEffect(() => {
    if (data) setDraft(cleanDocs(data.extracted));
  }, [data]);

  const done = (next: AuditDetail) => {
    queryClient.invalidateQueries();
    setNote('');
    navigate(`/case/${next.run_id}`);
  };
  const recheck = useMutation({
    mutationFn: () =>
      api.post(`/runs/${runId}/recheck`, { documents: toPayload(draft!) }).then((res) => res.data as AuditDetail),
    onSuccess: done,
  });
  const decide = useMutation({
    mutationFn: (decision: 'approve' | 'reject') =>
      api.post(`/runs/${runId}/decision`, { decision, note }).then((res) => res.data as AuditDetail),
    onSuccess: done,
  });

  const failures: Failure[] = useMemo(
    () => [...(data?.validation_failures ?? []), ...(data?.match_failures ?? [])],
    [data],
  );

  if (isLoading || (data && !draft)) return <div className="p-4">Loading case…</div>;
  if (isError || !data || !draft) return <div className="p-4 text-danger">Case not found.</div>;

  const latest = data.history.length ? data.history[data.history.length - 1].run_id : data.run_id;
  const isLatest = latest === data.run_id;
  // Mirrors the server rule: approved, or decided by a reviewer, is final.
  const closed = data.route === 'AUTO_APPROVE' || data.decided_by === 'reviewer';
  const canAct = isLatest && !closed;
  const busy = recheck.isPending || decide.isPending;
  const doc = draft[tab];

  const setField = (field: string, value: string) =>
    setDraft((prev) => (prev && prev[tab] ? { ...prev, [tab]: { ...prev[tab]!, [field]: value } } : prev));
  const setLine = (i: number, field: keyof LineItem, value: string) =>
    setDraft((prev) => {
      if (!prev || !prev[tab]) return prev;
      const lines = [...(prev[tab]!.line_items ?? [])];
      lines[i] = { ...lines[i], [field]: value };
      return { ...prev, [tab]: { ...prev[tab]!, line_items: lines } };
    });
  const addLine = () =>
    setDraft((prev) => {
      if (!prev || !prev[tab]) return prev;
      const lines = [...(prev[tab]!.line_items ?? [])];
      lines.push({ line_no: lines.length + 1, description: '', quantity: '', unit_price: null, amount: null });
      return { ...prev, [tab]: { ...prev[tab]!, line_items: lines } };
    });
  const removeLine = (i: number) =>
    setDraft((prev) => {
      if (!prev || !prev[tab]) return prev;
      const lines = (prev[tab]!.line_items ?? []).filter((_, j) => j !== i);
      return { ...prev, [tab]: { ...prev[tab]!, line_items: lines } };
    });

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Case header */}
      <div className="panel">
        <div className="panel-header flex justify-between items-center">
          <span className="flex items-center gap-2">
            <Link to="/review" className="text-blue-600 hover:underline flex items-center gap-1 font-normal">
              <ArrowLeft size={12} /> Review Queue
            </Link>
            <span className="text-gray-400">|</span>
            Case – Invoice <span className="font-mono text-navy">{data.invoice_number || 'N/A'}</span>
          </span>
          <span className="text-gray-500 text-[11px] font-normal">Customer: <b>{data.customer_id}</b></span>
        </div>
        <div className="p-3 flex gap-6 items-start">
          <div>
            <div className="text-[11px] text-gray-500 font-bold uppercase mb-1">Decision</div>
            <RouteChip route={data.route} />
            <div className="mt-1">{reasonLabel(data.route_reason)}</div>
            <div className="text-[11px] text-gray-500 mt-1">
              {data.decided_by === 'reviewer' ? (
                <>by <b>{data.reviewer ?? 'a reviewer'}</b></>
              ) : data.extraction_source === 'reviewer' ? (
                <>by the system, on values corrected by <b>{data.reviewer ?? 'a reviewer'}</b></>
              ) : (
                'by the system'
              )}
            </div>
          </div>
          <div className="flex-1">
            <div className="text-[11px] text-gray-500 font-bold uppercase mb-1">Summary</div>
            <div className="bg-gray-50 border border-gray-300 p-2">{data.remark}</div>
          </div>
          <div className="w-[260px]">
            <div className="text-[11px] text-gray-500 font-bold uppercase mb-1">History</div>
            <ul className="border border-gray-300 bg-white max-h-24 overflow-y-auto">
              {data.history.map((h) => (
                <li key={h.run_id} className={`px-2 py-0.5 border-b border-gray-200 text-[11px] flex justify-between ${h.run_id === data.run_id ? 'bg-blue-50 font-bold' : ''}`}>
                  <Link to={`/case/${h.run_id}`} className="text-blue-600 hover:underline" title={h.reviewer ? `by ${h.reviewer}` : 'by the system'}>{new Date(h.run_timestamp).toLocaleString()}</Link>
                  <RouteChip route={h.route} />
                </li>
              ))}
            </ul>
          </div>
        </div>
        {!isLatest && (
          <div className="mx-3 mb-3 p-2 bg-yellow-50 border border-yellow-300 text-[11px] flex items-center gap-2">
            <AlertTriangle size={14} className="text-warning" /> You are looking at an older step of this case.
            <Link to={`/case/${latest}`} className="text-blue-600 hover:underline font-bold">Open the latest</Link>
          </div>
        )}
      </div>

      {/* Problems */}
      <div className="panel">
        <div className="panel-header">
          {data.decided_by === 'reviewer' ? 'Problems the reviewer saw when deciding' : 'Problems found'} ({failures.length})
        </div>
        <div className="p-2">
          {failures.length === 0 ? (
            <div className="text-green-600 flex items-center gap-1"><CheckCircle2 size={14} /> No problems. All checks passed.</div>
          ) : (
            <ul className="space-y-1">
              {failures.map((f, i) => (
                <li key={i} className={`p-2 border text-[11px] ${f.severity === 'blocker' ? 'bg-red-50 border-red-200' : 'bg-orange-50 border-orange-200'}`}>
                  <b className={f.severity === 'blocker' ? 'text-red-700' : 'text-orange-700'}>{f.message || f.code}</b>
                  <span className="text-gray-500 ml-2 font-mono">[{f.code} · {f.location}]</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Document tabs: scan on the left, its fields on the right */}
      <div>
        <nav className="flex gap-[2px] px-1 border-b border-border">
          {DOC_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-1.5 border border-b-0 rounded-t-[5px] font-bold text-[12px] transition-colors
                ${tab === t.key ? 'bg-white border-border border-b-white text-[#222] relative top-[1px]' : 'bg-win7-panel border-border text-gray-600 hover:bg-gray-200'}`}
            >
              {t.label}{!draft[t.key] ? ' (missing)' : ''}
            </button>
          ))}
        </nav>
        <div className="flex gap-3 bg-white border border-t-0 border-border p-3">
          <div className="w-1/2">
            <div className="panel">
              <div className="panel-header">Scan</div>
              <div className="p-2 max-h-[640px] overflow-auto bg-gray-50">
                {draft[tab] ? (
                  <AuthImage path={`/documents/${data.run_id}/${tab}/image`} alt={`${tab} scan`} />
                ) : (
                  <div className="p-6 text-center text-gray-400">This document was not provided.</div>
                )}
              </div>
            </div>
          </div>

          <div className="w-1/2">
            <div className="panel">
              <div className="panel-header">
                {canAct ? 'Extracted data – correct anything the system misread' : 'Extracted data (read only)'}
              </div>
              <fieldset disabled={!canAct} className="contents">
              {!doc ? (
                <div className="p-4 text-gray-400">This document was not provided.</div>
              ) : (
                <div className="p-3">
                  <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                    {HEADER_FIELDS[tab].map((f) => (
                      <label key={f.name} className="flex flex-col">
                        <span className="text-[11px] text-gray-600 font-bold">{f.label}</span>
                        <input
                          type={f.type === 'date' ? 'date' : 'text'}
                          className="input-retro"
                          value={(doc[f.name] as string | null) ?? ''}
                          onChange={(e) => setField(f.name, e.target.value)}
                        />
                      </label>
                    ))}
                  </div>

                  {HAS_LINES[tab] && (
                    <div className="mt-3">
                      <div className="flex justify-between items-center mb-1">
                        <b className="text-[11px] uppercase text-gray-600">Line items</b>
                        <button className="btn-plain flex items-center gap-1 !py-0.5" onClick={addLine}>
                          <Plus size={12} /> Add line
                        </button>
                      </div>
                      <table className="w-full text-left border-collapse border border-gray-300">
                        <thead className="bg-win7-panel border-b border-gray-300">
                          <tr>
                            <th className="p-1 border-r border-gray-300 w-6">#</th>
                            <th className="p-1 border-r border-gray-300">Description</th>
                            <th className="p-1 border-r border-gray-300 w-16">Qty</th>
                            {LINE_MONEY[tab] && <th className="p-1 border-r border-gray-300 w-24">Unit price</th>}
                            {LINE_MONEY[tab] && <th className="p-1 border-r border-gray-300 w-24">Amount</th>}
                            <th className="p-1 w-6"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {(doc.line_items ?? []).map((li, i) => (
                            <tr key={i} className="border-b border-gray-200">
                              <td className="p-1 text-gray-500">{i + 1}</td>
                              <td className="p-1"><input className="input-retro w-full" value={li.description ?? ''} onChange={(e) => setLine(i, 'description', e.target.value)} /></td>
                              <td className="p-1"><input className="input-retro w-full" value={li.quantity ?? ''} onChange={(e) => setLine(i, 'quantity', e.target.value)} /></td>
                              {LINE_MONEY[tab] && <td className="p-1"><input className="input-retro w-full" value={li.unit_price ?? ''} onChange={(e) => setLine(i, 'unit_price', e.target.value)} /></td>}
                              {LINE_MONEY[tab] && <td className="p-1"><input className="input-retro w-full" value={li.amount ?? ''} onChange={(e) => setLine(i, 'amount', e.target.value)} /></td>}
                              <td className="p-1 text-center">
                                <button onClick={() => removeLine(i)} title="Remove line" aria-label="Remove line" className="text-gray-400 hover:text-danger">
                                  <Trash2 size={12} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
              </fieldset>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="panel">
        <div className="panel-header">Decide</div>
        {isLatest && closed ? (
          <div className="p-3 flex items-center gap-2 text-[12px]">
            <Lock size={14} className="text-gray-500" />
            This case is closed: it was {data.route === 'AUTO_APPROVE' ? 'approved' : 'rejected'} by {data.reviewer ?? (data.decided_by === 'reviewer' ? 'a reviewer' : 'the system')}.
            A final decision cannot be changed here; the history above keeps every step.
          </div>
        ) : (
        <div className="p-3 flex gap-4 items-start">
          <div className="w-1/3">
            <button className="btn flex items-center gap-1" disabled={busy || !canAct || !draft.invoice} onClick={() => recheck.mutate()}>
              <RefreshCw size={12} className={recheck.isPending ? 'animate-spin' : ''} /> Save &amp; Re-check
            </button>
            <p className="text-[11px] text-gray-600 mt-2">
              Runs every check again on the values above (no re-reading of the scan). If everything now agrees, the case is approved automatically.
            </p>
            {recheck.isError && <p className="text-danger text-[11px] mt-1">{errorText(recheck.error)}</p>}
          </div>
          <div className="flex-1">
            <label className="flex flex-col">
              <span className="text-[11px] text-gray-600 font-bold">Reviewer note (required to approve or reject)</span>
              <textarea
                className="input-retro h-14 resize-y"
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Called the supplier: price increase agreed by email on 12 Nov."
              />
            </label>
            <div className="flex gap-2 mt-2">
              <button className="btn-plain flex items-center gap-1 text-green-800" disabled={busy || !canAct || !note.trim()} onClick={() => decide.mutate('approve')}>
                <CheckCircle2 size={12} /> Approve for payment
              </button>
              <button className="btn-plain flex items-center gap-1 text-red-700" disabled={busy || !canAct || !note.trim()} onClick={() => decide.mutate('reject')}>
                <XCircle size={12} /> Reject
              </button>
            </div>
            {decide.isError && <p className="text-danger text-[11px] mt-1">{errorText(decide.error)}</p>}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
