import { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { UploadCloud, CheckCircle, AlertCircle, FileText, Loader2, FolderOpen } from 'lucide-react';
import api from '../api/client';
import { reasonLabel } from '../api/types';
import RouteChip from '../components/RouteChip';
import { useCustomer } from '../customer';

type DocType = 'inv' | 'po' | 'grn' | 'pard';

interface FileSet {
  id: string;
  files: Partial<Record<DocType, File>>;
  status: 'pending' | 'processing' | 'success' | 'error';
  result?: any;
}

export default function UploadBatch() {
  const { customer } = useCustomer();
  const queryClient = useQueryClient();
  const [sets, setSets] = useState<FileSet[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const processFiles = (files: File[]) => {
    const groups = new Map<string, FileSet>();
    const groupFor = (key: string) => {
      let set = groups.get(key);
      if (!set) {
        set = { id: key, files: {}, status: 'pending' };
        groups.set(key, set);
      }
      return set;
    };

    files.forEach((file) => {
      const type = docTypeOf(file.name);
      if (!type) return; // not an INV / PO / GRN / PARD file (e.g. labels.csv)
      // A folder upload ("CASE-0001/INV_....jpg") groups by folder: one folder = one case.
      const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || '';
      const parts = path.split('/').filter(Boolean);
      let key: string;
      if (parts.length >= 2) {
        key = parts[parts.length - 2];
      } else if (files.length <= 4) {
        key = 'SET-1'; // up to four loose files: one case
      } else {
        // Loose files: group on the number after the prefix ("INV-123.pdf" + "PO-123.png").
        const m = file.name.match(/^[A-Za-z]+[_-]+(.+?)\.[^.]+$/);
        key = m ? m[1] : file.name;
      }
      groupFor(key).files[type] = file;
    });

    const newSets = Array.from(groups.values()).sort((x, y) => x.id.localeCompare(y.id));
    setSets((prev) => [...prev, ...newSets]);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      processFiles(Array.from(e.dataTransfer.files));
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      processFiles(Array.from(e.target.files));
    }
  };

  const runBatch = async () => {
    setIsProcessing(true);
    const updatedSets = [...sets];

    for (let i = 0; i < updatedSets.length; i++) {
      const set = updatedSets[i];

      // FIX: Don't send to API if there is no invoice
      if (!set.files.inv) {
        updatedSets[i] = { ...set, status: 'error', result: { route: 'MISSING INVOICE' } };
        setSets([...updatedSets]);
        continue;
      }

      if (set.status === 'success') continue;

      updatedSets[i] = { ...set, status: 'processing' };
      setSets([...updatedSets]);

      try {
        const formData = new FormData();
        formData.append('invoice', set.files.inv);
        if (set.files.po) formData.append('po', set.files.po);
        if (set.files.grn) formData.append('grni', set.files.grn);
        if (set.files.pard) formData.append('pard', set.files.pard);

        const res = await api.post('/match', formData, { params: { customer_id: customer } });
        updatedSets[i] = { ...updatedSets[i], status: 'success', result: res.data };
      } catch (err: any) {
        console.error(err);
        updatedSets[i] = { ...updatedSets[i], status: 'error', result: { route: err.response?.data?.detail || 'API ERROR' } };
      }
      setSets([...updatedSets]);
    }
    setIsProcessing(false);
    queryClient.invalidateQueries();
  };

  return (
    <div className="p-4">
      <div className="flex gap-4">

        {/* Left Side: Dropzone */}
        <div className="w-1/3 flex flex-col gap-3">
          <div className="panel">
            <div className="panel-header">Batch Intake</div>
            <div className="p-4">
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-400 bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer flex flex-col items-center justify-center p-8 text-center h-48"
              >
                <UploadCloud size={32} className="text-gray-400 mb-2" />
                <b className="text-navy">Drag & Drop Documents</b>
                <span className="text-gray-500 mt-1">or click to browse files</span>
                <input
                  type="file"
                  multiple
                  className="hidden"
                  ref={fileInputRef}
                  onChange={onFileChange}
                  accept="image/*"
                />
              </div>
              <input
                type="file"
                multiple
                className="hidden"
                ref={folderInputRef}
                onChange={onFileChange}
                {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
              />
              <div className="mt-3 flex items-center justify-between">
                <button className="btn-plain flex items-center gap-1" onClick={() => folderInputRef.current?.click()}>
                  <FolderOpen size={14} /> Choose Folder…
                </button>
                <span className="text-[11px] text-gray-600">Customer: <b className="text-navy">{customer}</b></span>
              </div>
              <div className="mt-3 text-[11px] text-gray-600">
                <p className="font-bold mb-1">Grouping Rules:</p>
                <ul className="list-disc pl-4 space-y-1">
                  <li>File names start with <code className="bg-gray-200 px-1">INV</code>, <code className="bg-gray-200 px-1">PO</code>, <code className="bg-gray-200 px-1">GRN</code> or <code className="bg-gray-200 px-1">PARD</code>.</li>
                  <li>Choosing a folder: every sub-folder is one case (e.g. <code className="bg-gray-200 px-1">CASE-0001/</code>).</li>
                  <li>Up to four loose files form one case; more are grouped by the number in the name (<code className="bg-gray-200 px-1">INV-123.png</code> + <code className="bg-gray-200 px-1">PO-123.png</code>).</li>
                  <li>Images only (PNG, JPG). PDF support is coming.</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Right Side: Grouped Sets */}
        <div className="w-2/3 flex flex-col gap-3">
          <div className="panel flex-1">
            <div className="panel-header flex justify-between items-center">
              <span>Detected Document Sets ({sets.length})</span>
              {sets.length > 0 && (
                <button
                  className="btn flex items-center gap-1"
                  onClick={runBatch}
                  disabled={isProcessing}
                >
                  {isProcessing ? <Loader2 size={14} className="animate-spin" /> : null}
                  {isProcessing ? 'Processing...' : 'Process Batch'}
                </button>
              )}
            </div>

            <div className="p-2 h-[500px] overflow-y-auto bg-gray-50">
              {sets.length === 0 ? (
                <div className="flex h-full items-center justify-center text-gray-400">
                  No documents dropped yet.
                </div>
              ) : (
                <table className="w-full text-left border-collapse bg-white border border-gray-300 shadow-sm">
                  <thead className="bg-win7-panel border-b border-gray-300">
                    <tr>
                      <th className="p-2 border-r border-gray-300">Reference ID</th>
                      <th className="p-2 border-r border-gray-300 text-center">INV</th>
                      <th className="p-2 border-r border-gray-300 text-center">PO</th>
                      <th className="p-2 border-r border-gray-300 text-center">GRN</th>
                      <th className="p-2 border-r border-gray-300 text-center">PARD</th>
                      <th className="p-2 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sets.map((set, idx) => {
                      // Check how many of the 4 required docs we have
                      const count = Object.values(set.files).filter(Boolean).length;
                      const isComplete = count === 4;

                      return (
                      <tr key={idx} className={`border-b border-gray-200 hover:bg-gray-50 ${!isComplete ? 'bg-red-50' : ''}`}>
                        <td className="p-2 font-mono font-bold text-navy flex items-center gap-2">
                          {set.id}
                          {!isComplete && (
                            <span className="text-[10px] bg-red-200 text-red-800 px-1 rounded border border-red-300">
                              Incomplete ({count}/4)
                            </span>
                          )}
                        </td>
                        <td className="p-2 text-center">{set.files.inv ? <FileIcon name="INV" /> : <span className="text-red-300">Missing</span>}</td>
                        <td className="p-2 text-center">{set.files.po ? <FileIcon name="PO" /> : <span className="text-red-300">Missing</span>}</td>
                        <td className="p-2 text-center">{set.files.grn ? <FileIcon name="GRN" /> : <span className="text-red-300">Missing</span>}</td>
                        <td className="p-2 text-center">{set.files.pard ? <FileIcon name="PARD" /> : <span className="text-red-300">Missing</span>}</td>
                        <td className="p-2 text-center">
                          {set.status === 'pending' && <span className="text-gray-500 font-bold">Ready</span>}
                          {set.status === 'processing' && <span className="text-warning font-bold flex items-center justify-center gap-1"><Loader2 size={12} className="animate-spin"/> OCR...</span>}
                          {set.status === 'success' && (
                            <div className="flex flex-col items-center gap-1">
                              <span className="flex items-center gap-1"><CheckCircle size={12} className="text-success"/> <RouteChip route={set.result?.route} /></span>
                              <span className="text-[10px] text-gray-600">{reasonLabel(set.result?.route_reason)}</span>
                              <Link to={`/case/${set.result?.run_id}`} className="text-[10px] text-blue-600 hover:underline">Open case</Link>
                            </div>
                          )}
                          {set.status === 'error' && (
                            <span className="text-danger font-bold flex items-center justify-center gap-1 text-[10px]" title={set.result?.route}>
                              <AlertCircle size={12}/> {set.result?.route || 'Failed'}
                            </span>
                          )}
                        </td>
                      </tr>
                    )})}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// INV_..., PO_..., GRN_... / RCV_..., PARD_... / PAY_... (the prefix decides the type).
function docTypeOf(fileName: string): DocType | null {
  const name = fileName.toUpperCase();
  if (name.startsWith('INV')) return 'inv';
  if (name.startsWith('PARD') || name.startsWith('PAY')) return 'pard';
  if (name.startsWith('PO')) return 'po';
  if (name.startsWith('GRN') || name.startsWith('RCV')) return 'grn';
  return null;
}

// Small helper component for the table
function FileIcon({ name }: { name: string }) {
  return (
    <div className="inline-flex items-center gap-1 text-[10px] bg-blue-100 text-blue-800 border border-blue-300 px-1 rounded">
      <FileText size={10} /> {name}
    </div>
  );
}
