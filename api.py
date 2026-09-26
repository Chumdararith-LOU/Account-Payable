"""DPAI API - bridge between Power Platform and your existing engine"""
import os
import json
import traceback
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from pp import process_document
from ai_engine import run_matching_engine
from database import (
    extract_po_from_json,
    extract_grni_from_json,
    extract_invoice_from_json,
    extract_pard_from_json,
    get_dashboard_stats,
)

app = FastAPI(title="DPAI Service", version="1.1")

# ---------- SECURITY ----------
API_KEY = "DPAI-DEMO-2026"          # change to your own secret
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")

# ---------- CORE ----------
EXTRACTORS = {
    "PO": extract_po_from_json,
    "GRNI": extract_grni_from_json,
    "INVOICE": extract_invoice_from_json,
    "PARD": extract_pard_from_json,
}

SAMPLE_DIR = "output/ocr"

class ProcessRequest(BaseModel):
    doc_type: str
    raw: dict

class DirectRequest(BaseModel):
    doc_type: str
    doc_data: dict

def guess_doc_type(filename: str) -> str:
    name = filename.upper()
    if name.startswith("PO"):   return "PO"
    if name.startswith("GRN"):  return "GRNI"
    if name.startswith("PARD"): return "PARD"
    return "INVOICE"

def run_pipeline(doc_type: str, raw: dict):
    doc_type = doc_type.upper()
    if doc_type not in EXTRACTORS:
        raise ValueError(f"doc_type must be one of {list(EXTRACTORS)}")
    doc_data = EXTRACTORS[doc_type](raw)
    if doc_data is None:
        raise ValueError(f"Could not parse JSON as {doc_type}")
    saved = process_document(doc_data, doc_type)
    matching = None
    if doc_type == "INVOICE" and saved and not doc_data.get("is_duplicate"):
        inv_id = doc_data.get("inv_id")
        if inv_id:
            run_matching_engine(inv_id)
            matching = "executed"
    return {
        "saved": saved,
        "is_duplicate": bool(doc_data.get("is_duplicate", False)),
        "doc_type": doc_type,
        "doc_data": doc_data,
        "matching": matching,
    }

def safe_run(doc_type, payload_builder):
    try:
        return run_pipeline(doc_type, payload_builder())
    except Exception as e:
        return {"ERROR_CAUGHT": str(e), "ERROR_TYPE": type(e).__name__,
                "TRACEBACK": traceback.format_exc()}

# ---------- PUBLIC ENDPOINTS ----------
@app.get("/health")
def health():
    return {"status": "ok", "doc_types": list(EXTRACTORS)}

@app.get("/samples")
def list_samples():
    files = sorted(f for f in os.listdir(SAMPLE_DIR) if f.endswith(".json"))
    return {"samples": files}

# ---------- PROTECTED ENDPOINTS ----------
@app.get("/stats")
def stats(_: str = Depends(require_api_key)):
    return get_dashboard_stats()

@app.post("/process")
def process(req: ProcessRequest, _: str = Depends(require_api_key)):
    return safe_run(req.doc_type, lambda: req.raw)

@app.post("/process-direct")
def process_direct(req: DirectRequest, _: str = Depends(require_api_key)):
    try:
        doc_type = req.doc_type.upper()
        doc_data = req.doc_data
        saved = process_document(doc_data, doc_type)
        matching = None
        if doc_type == "INVOICE" and saved and not doc_data.get("is_duplicate"):
            inv_id = doc_data.get("inv_id")
            if inv_id:
                run_matching_engine(inv_id)
                matching = "executed"
        return {"saved": saved,
                "is_duplicate": bool(doc_data.get("is_duplicate", False)),
                "doc_type": doc_type, "doc_data": doc_data, "matching": matching}
    except Exception as e:
        return {"ERROR_CAUGHT": str(e), "ERROR_TYPE": type(e).__name__,
                "TRACEBACK": traceback.format_exc()}

@app.post("/process-file")
def process_file(payload: dict, _: str = Depends(require_api_key)):
    filename = os.path.basename(payload.get("filename", ""))
    path = os.path.join(SAMPLE_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Sample file not found")
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return safe_run(guess_doc_type(filename), lambda: raw)

# ---------- DEMO WEB PAGE ----------
DEMO_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DPAI Demo</title><style>
body{font-family:'Segoe UI',Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}
.card{background:#1e293b;border-radius:12px;padding:20px;margin:0 auto 16px;max-width:900px}
h1{margin:0 0 8px;font-size:22px} h2{font-size:16px;margin:0 0 12px}
button{background:#2563eb;color:#fff;border:0;padding:10px 18px;border-radius:8px;cursor:pointer;font-size:14px}
button:hover{background:#1d4ed8}
select,input{padding:8px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;margin-right:8px}
table{width:100%;border-collapse:collapse;margin-top:10px}
td,th{padding:6px 10px;border-bottom:1px solid #334155;text-align:left;font-size:14px}
.ok{color:#4ade80}.bad{color:#f87171}.warn{color:#fbbf24}
</style></head><body>
<div class="card"><h1>🧾 DPAI Demo — Document Processing & 3-Way Matching</h1>
<p id="health">Checking service…</p>
<label>API Key: <input id="apikey" type="password" placeholder="enter demo key" size="28"></label></div>
<div class="card"><h2>1️⃣ Run a sample document</h2>
<select id="sample"></select><button onclick="runSample()">Process Document</button></div>
<div class="card"><h2>2️⃣ Or upload an OCR JSON file</h2>
<input type="file" id="file" accept=".json">
<select id="doctype"><option>INVOICE</option><option>PO</option><option>GRNI</option><option>PARD</option></select>
<button onclick="runUpload()">Process Upload</button></div>
<div class="card" id="resultCard" style="display:none"><h2>Result</h2><div id="result"></div></div>
<div class="card"><h2>Run history</h2>
<table id="history"><tr><th>Time</th><th>Type</th><th>Doc No</th><th>Vendor</th><th>Total</th><th>Saved</th><th>Duplicate</th><th>Matching</th></tr></table></div>
<script>
const $=id=>document.getElementById(id);
async function api(path,opts={}){opts.headers=Object.assign({'X-API-Key':$('apikey').value,'Content-Type':'application/json'},opts.headers||{});const r=await fetch(path,opts);return r.json();}
fetch('/health').then(r=>r.json()).then(d=>{$('health').innerHTML='Service: <span class="ok">● online</span> — supports '+d.doc_types.join(', ');})
 .catch(()=>{$('health').innerHTML='Service: <span class="bad">● offline</span>';});
api('/samples').then(d=>{$('sample').innerHTML=d.samples.map(s=>'<option>'+s+'</option>').join('');});
function show(res){$('resultCard').style.display='block';const dd=res.doc_data||{};
 if(res.ERROR_CAUGHT||res.detail){$('result').innerHTML='<p class="bad">Error: '+(res.ERROR_CAUGHT||res.detail)+'</p>';return;}
 let h='<p>Saved: <span class="'+(res.saved?'ok':'bad')+'">'+res.saved+'</span> &nbsp;|&nbsp; Duplicate: <span class="'+(res.is_duplicate?'warn':'ok')+'">'+res.is_duplicate+'</span> &nbsp;|&nbsp; Matching: '+(res.matching||'—')+'</p>';
 h+='<table><tr><th>Field</th><th>Value</th></tr><tr><td>Doc type</td><td>'+res.doc_type+'</td></tr>'
 +'<tr><td>Document No</td><td>'+(dd.inv_id||dd.po_id||dd.grni_id||dd.pard_id||'—')+'</td></tr>'
 +'<tr><td>Vendor</td><td>'+(dd.vendor||'—')+'</td></tr><tr><td>Date</td><td>'+(dd.date||'—')+'</td></tr>'
 +'<tr><td>Total</td><td>'+(dd.total??'—')+'</td></tr><tr><td>Tax</td><td>'+(dd.tax??'—')+'</td></tr></table>';
 if(dd.lines&&dd.lines.length){h+='<table><tr><th>Item</th><th>Qty</th><th>Price</th></tr>'
  +dd.lines.map(l=>'<tr><td>'+l.item+'</td><td>'+l.qty+'</td><td>'+l.price+'</td></tr>').join('')+'</table>';}
 $('result').innerHTML=h;
 $('history').insertAdjacentHTML('beforeend','<tr><td>'+new Date().toLocaleTimeString()+'</td><td>'+res.doc_type
  +'</td><td>'+(dd.inv_id||dd.po_id||'—')+'</td><td>'+(dd.vendor||'—')+'</td><td>'+(dd.total??'—')
  +'</td><td>'+res.saved+'</td><td>'+res.is_duplicate+'</td><td>'+(res.matching||'—')+'</td></tr>');}
async function runSample(){show(await api('/process-file',{method:'POST',body:JSON.stringify({filename:$('sample').value})}));}
async function runUpload(){const f=$('file').files[0];if(!f){alert('Choose a .json file first');return;}
 const raw=JSON.parse(await f.text());show(await api('/process',{method:'POST',body:JSON.stringify({doc_type:$('doctype').value,raw:raw})}));}
</script></body></html>
"""

@app.get("/", response_class=HTMLResponse)
def demo_page():
    return DEMO_HTML