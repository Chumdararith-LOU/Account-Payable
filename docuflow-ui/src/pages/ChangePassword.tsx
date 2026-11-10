import { useState, type FormEvent } from 'react';
import { Lock, Loader2 } from 'lucide-react';
import { apiErrorText } from '../api/client';
import { useAuth } from '../auth';

const MIN_LENGTH = 10;

/** Change your own password. ``forced`` = first sign-in with a temporary password. */
export default function ChangePassword({ forced = false }: { forced?: boolean }) {
  const { changePassword, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const mismatch = again.length > 0 && next !== again;
  const tooShort = next.length > 0 && next.length < MIN_LENGTH;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await changePassword(current, next);
      setDone(true);
      setCurrent('');
      setNext('');
      setAgain('');
    } catch (err) {
      setError(apiErrorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 flex justify-center">
      <form onSubmit={submit} className="panel w-[420px]">
        <div className="panel-header flex items-center gap-2">
          <Lock size={14} /> {forced ? 'Choose your own password' : 'Change password'}
        </div>
        <div className="p-4 space-y-3">
          {forced && (
            <p className="p-2 bg-yellow-50 border border-yellow-300 text-[11px]">
              You signed in with a temporary password. Choose your own before you continue.
            </p>
          )}
          {done && !forced && (
            <p className="p-2 bg-green-50 border border-green-300 text-[11px]">
              Password changed. Other devices were signed out.
            </p>
          )}
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-gray-600 font-bold">{forced ? 'Temporary password' : 'Current password'}</span>
            <input className="input-retro" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-gray-600 font-bold">New password (at least {MIN_LENGTH} characters)</span>
            <input className="input-retro" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-gray-600 font-bold">New password again</span>
            <input className="input-retro" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required />
          </label>
          {tooShort && <p className="text-warning text-[11px]">Too short.</p>}
          {mismatch && <p className="text-warning text-[11px]">The two new passwords differ.</p>}
          {error && <p className="text-danger text-[11px]">{error}</p>}
          <div className="flex justify-between pt-1">
            {forced ? (
              <button type="button" className="btn-plain" onClick={() => logout()}>Sign out</button>
            ) : <span />}
            <button className="btn flex items-center gap-1" disabled={busy || !current || tooShort || mismatch || !next || next !== again}>
              {busy && <Loader2 size={12} className="animate-spin" />} Save Password
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
