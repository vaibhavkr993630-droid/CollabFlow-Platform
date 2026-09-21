import { useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { errorMessage } from '../lib/format'
import type { MemberUser, Role } from '../types'
import { Avatar } from './Avatar'

interface MemberRow {
  id: string
  user_id: string
  role: Role
  user: MemberUser
}

const ROLE_STYLES: Record<Role, string> = {
  owner: 'bg-purple-100 text-purple-700',
  admin: 'bg-amber-100 text-amber-700',
  member: 'bg-gray-100 text-gray-600',
}

const ROLE_HELP: Record<Role, string> = {
  owner: 'Full control',
  admin: 'Can add people',
  member: 'Can view and edit work',
}

export function RoleBadge({ role }: { role: Role }) {
  return (
    <span
      title={ROLE_HELP[role]}
      className={`rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${ROLE_STYLES[role]}`}
    >
      {role}
    </span>
  )
}

/**
 * A member list with an "add by email" form. Used for both workspaces and
 * projects: the caller supplies the rows and the invite call, this component
 * owns the form state and decides who may see the form (owners and admins —
 * the same rule the backend enforces with a 403).
 */
export function MembersPanel({
  noun,
  members,
  isLoading,
  onInvite,
}: {
  noun: 'workspace' | 'project'
  members: MemberRow[]
  isLoading: boolean
  onInvite: (email: string, role: Role) => Promise<unknown>
}) {
  const { user } = useAuth()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('member')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const myRole = members.find((m) => m.user_id === user?.id)?.role
  const canInvite = myRole === 'owner' || myRole === 'admin'

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = email.trim()
    if (!trimmed) return
    setError(null)
    setNotice(null)
    setPending(true)
    try {
      await onInvite(trimmed, role)
      setNotice(`Added ${trimmed} as ${role}.`)
      setEmail('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <div>
      {isLoading ? (
        <p className="text-sm text-gray-400">Loading members…</p>
      ) : (
        <ul className="divide-y divide-gray-100">
          {members.map((member) => (
            <li key={member.id} className="flex items-center gap-3 py-2">
              <Avatar name={member.user.full_name} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-900">
                  {member.user.full_name}
                  {member.user_id === user?.id && (
                    <span className="ml-1 text-xs font-normal text-gray-400">(you)</span>
                  )}
                </p>
                <p className="truncate text-xs text-gray-500">{member.user.email}</p>
              </div>
              <RoleBadge role={member.role} />
            </li>
          ))}
        </ul>
      )}

      {canInvite ? (
        <form onSubmit={handleSubmit} className="mt-4 border-t border-gray-100 pt-4">
          <label htmlFor={`invite-${noun}`} className="mb-1 block text-xs font-medium text-gray-500">
            Add someone to this {noun}
          </label>
          <div className="flex gap-2">
            <input
              id={`invite-${noun}`}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teammate@example.com"
              className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              aria-label="Role"
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <button
              type="submit"
              disabled={pending || !email.trim()}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {pending ? 'Adding…' : 'Add'}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-gray-400">
            They need a CollabFlow account already. Members can view and edit work; admins can
            also add people.
          </p>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          {notice && <p className="mt-2 text-sm text-green-600">{notice}</p>}
        </form>
      ) : (
        !isLoading && (
          <p className="mt-4 border-t border-gray-100 pt-4 text-xs text-gray-400">
            Only owners and admins can add people to a {noun}.
          </p>
        )
      )}
    </div>
  )
}
