import { useState, type FormEvent } from 'react';
import { KeyRound, Loader2 } from 'lucide-react';
import { apiErrorText } from '../api/client';
import Brand from '../components/Brand';
import { useAuth } from '../auth';

export default function SignIn() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(apiErrorText(err));
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-bg">
      <header className="bg-win7 border-b-[3px] border-navy-dark text-white flex items-center p-2 px-4 shadow-md">
        <Brand />
      </header>
      <main className="flex-1 flex items-start justify-center pt-20">
        <form onSubmit={submit} className="panel w-[360px]">
          <div className="panel-header flex items-center gap-2">
            <KeyRound size={14} /> Sign in
          </div>
          <div className="p-4 space-y-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-gray-600 font-bold">Username</span>
              <input
                className="input-retro"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-gray-600 font-bold">Password</span>
              <input
                className="input-retro"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            {error && <p className="text-danger text-[11px]">{error}</p>}
            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-gray-500">Your administrator creates accounts.</span>
              <button className="btn flex items-center gap-1" disabled={busy || !username || !password}>
                {busy && <Loader2 size={12} className="animate-spin" />} Sign In
              </button>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}
