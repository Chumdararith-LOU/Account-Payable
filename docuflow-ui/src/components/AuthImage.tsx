import { useEffect, useState } from 'react';
import api from '../api/client';

// Document scans need the X-API-Key header, which a plain <img src> cannot
// send: fetch the bytes with the API client and show them from a blob URL.
export default function AuthImage({ path, alt }: { path: string; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setUrl(null);
    setFailed(false);
    api
      .get(path, { responseType: 'blob' })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setUrl(objectUrl);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (failed) return <div className="p-6 text-center text-gray-400">No scan stored for this document.</div>;
  if (!url) return <div className="p-6 text-center text-gray-400">Loading scan…</div>;
  return <img src={url} alt={alt} className="w-full h-auto border border-border bg-white" />;
}
