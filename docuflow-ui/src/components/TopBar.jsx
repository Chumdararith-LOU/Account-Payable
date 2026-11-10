import React from 'react';
import { Building2, Settings } from 'lucide-react';

export default function TopBar() {
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
          <label className="font-bold text-[11px] uppercase tracking-wider text-gray-200">Customer:</label>
          <select className="bg-[#cfd9e4] text-navy-dark font-bold text-[13px] px-1 py-0.5 border border-navy-dark rounded-[3px] outline-none">
            <option>Acme Manufacturing</option>
            <option>Globex Logistics</option>
            <option>default</option>
          </select>
        </div>
        <button className="text-gray-300 hover:text-white transition-colors">
          <Settings size={18} />
        </button>
      </div>
    </header>
  );
}
