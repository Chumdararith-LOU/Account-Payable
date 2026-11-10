import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, UserPlus, Users as UsersIcon } from 'lucide-react';
import api, { apiErrorText } from '../api/client';
import { useAuth, type User } from '../auth';

interface Created {
  user: User;
  temporary_password: string;
}

/** Admin only: add people, reset passwords, switch accounts off. */
export default function Users() {
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<'reviewer' | 'admin'>('reviewer');
  const [issued, setIssued] = useState<Created | null>(null);

  const { data: users, isLoading } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then((res) => res.data),
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<Created>('/users', { username: username.trim().toLowerCase(), display_name: displayName.trim(), role }).then((r) => r.data),
    onSuccess: (data) => {
      setIssued(data);
      setUsername('');
      setDisplayName('');
      setRole('reviewer');
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  const update = useMutation({
    mutationFn: ({ name, body }: { name: string; body: Record<string, unknown> }) =>
      api.patch<Created | User>(`/users/${encodeURIComponent(name)}`, body).then((r) => r.data),
    onSuccess: (data) => {
      if ('temporary_password' in data) setIssued(data);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setIssued(null);
    create.mutate();
  };

  const confirmReset = (u: User) => {
    if (window.confirm(`Give ${u.display_name} a new temporary password? Their current password stops working.`)) {
      setIssued(null);
      update.mutate({ name: u.username, body: { reset_password: true } });
    }
  };

  return (
    <div className="p-4 flex gap-4 items-start">
      <div className="panel flex-1">
        <div className="panel-header flex items-center gap-2">
          <UsersIcon size={14} /> Users ({users?.length ?? 0})
        </div>
        <table className="w-full text-left border-collapse">
          <thead className="bg-win7-panel border-b border-border">
            <tr>
              <th className="p-2 border-r border-border font-bold">Username</th>
              <th className="p-2 border-r border-border font-bold">Name</th>
              <th className="p-2 border-r border-border font-bold">Role</th>
              <th className="p-2 border-r border-border font-bold">Status</th>
              <th className="p-2 font-bold"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="p-4 text-center text-gray-500">Loading…</td></tr>
            )}
            {users?.map((u) => {
              const self = u.username === me?.username;
              return (
                <tr key={u.username} className={`border-b border-gray-200 ${u.active ? '' : 'text-gray-400'}`}>
                  <td className="p-2 font-mono">{u.username}</td>
                  <td className="p-2">{u.display_name}{self && <span className="text-gray-500"> (you)</span>}</td>
                  <td className="p-2">
                    <select
                      className="input-retro"
                      value={u.role}
                      disabled={self || update.isPending}
                      onChange={(e) => update.mutate({ name: u.username, body: { role: e.target.value } })}
                    >
                      <option value="reviewer">Reviewer</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="p-2 text-[11px]">
                    {!u.active ? 'Switched off' : u.must_change_password ? 'Must choose a password' : 'Active'}
                  </td>
                  <td className="p-2 text-right whitespace-nowrap">
                    <button className="btn-plain text-[11px] mr-1" disabled={self || update.isPending} onClick={() => confirmReset(u)}>
                      Reset password
                    </button>
                    <button
                      className="btn-plain text-[11px]"
                      disabled={self || update.isPending}
                      onClick={() => update.mutate({ name: u.username, body: { active: !u.active } })}
                    >
                      {u.active ? 'Switch off' : 'Switch on'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {update.isError && <p className="text-danger text-[11px] p-2">{apiErrorText(update.error)}</p>}
      </div>

      <div className="w-[340px] space-y-4">
        <form onSubmit={submit} className="panel">
          <div className="panel-header flex items-center gap-2">
            <UserPlus size={14} /> Add a person
          </div>
          <div className="p-3 space-y-2">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-gray-600 font-bold">Username (lowercase, e.g. sokha.chan)</span>
              <input className="input-retro" value={username} onChange={(e) => setUsername(e.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-gray-600 font-bold">Full name</span>
              <input className="input-retro" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] text-gray-600 font-bold">Role</span>
              <select className="input-retro" value={role} onChange={(e) => setRole(e.target.value as 'reviewer' | 'admin')}>
                <option value="reviewer">Reviewer – reviews and decides cases</option>
                <option value="admin">Admin – also manages users</option>
              </select>
            </label>
            {create.isError && <p className="text-danger text-[11px]">{apiErrorText(create.error)}</p>}
            <div className="flex justify-end">
              <button className="btn" disabled={create.isPending || !username.trim() || !displayName.trim()}>Create User</button>
            </div>
          </div>
        </form>

        {issued && (
          <div className="panel">
            <div className="panel-header flex items-center gap-2">
              <KeyRound size={14} /> Temporary password
            </div>
            <div className="p-3 text-[11px] space-y-2">
              <p>
                Give this to <b>{issued.user.display_name}</b> ({issued.user.username}). It is shown only once; they
                choose their own password at first sign-in.
              </p>
              <div className="p-2 bg-yellow-50 border border-yellow-300 font-mono text-[14px] select-all text-center">
                {issued.temporary_password}
              </div>
              <div className="flex justify-end">
                <button className="btn-plain text-[11px]" onClick={() => setIssued(null)}>Done</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
