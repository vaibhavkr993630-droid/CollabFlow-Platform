import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import * as orgApi from '../api/organizations'
import * as projectApi from '../api/projects'
import { Layout } from '../components/Layout'

export default function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const orgId = searchParams.get('org')
  const workspaceId = searchParams.get('workspace')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [newOrgName, setNewOrgName] = useState('')
  const [newWorkspaceName, setNewWorkspaceName] = useState('')
  const [newProjectName, setNewProjectName] = useState('')

  const orgsQuery = useQuery({
    queryKey: ['organizations'],
    queryFn: orgApi.listOrganizations,
  })

  const workspacesQuery = useQuery({
    queryKey: ['workspaces', orgId],
    queryFn: () => orgApi.listWorkspaces(orgId!),
    enabled: !!orgId,
  })

  const projectsQuery = useQuery({
    queryKey: ['projects', workspaceId],
    queryFn: () => projectApi.listProjects(workspaceId!),
    enabled: !!workspaceId,
  })

  const createOrg = useMutation({
    mutationFn: orgApi.createOrganization,
    onSuccess: (org) => {
      void queryClient.invalidateQueries({ queryKey: ['organizations'] })
      setNewOrgName('')
      setSearchParams({ org: org.id })
    },
  })

  const createWorkspace = useMutation({
    mutationFn: (name: string) => orgApi.createWorkspace(orgId!, name),
    onSuccess: (workspace) => {
      void queryClient.invalidateQueries({ queryKey: ['workspaces', orgId] })
      setNewWorkspaceName('')
      setSearchParams({ org: orgId!, workspace: workspace.id })
    },
  })

  const createProject = useMutation({
    mutationFn: (name: string) => projectApi.createProject(workspaceId!, { name }),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ['projects', workspaceId] })
      setNewProjectName('')
      navigate(`/projects/${project.id}`)
    },
  })

  return (
    <Layout>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <Column title="Organizations">
          {orgsQuery.data?.map((org) => (
            <ListItem
              key={org.id}
              label={org.name}
              selected={org.id === orgId}
              onClick={() => setSearchParams({ org: org.id })}
            />
          ))}
          <CreateForm
            placeholder="New organization name"
            value={newOrgName}
            onChange={setNewOrgName}
            onSubmit={() => newOrgName.trim() && createOrg.mutate(newOrgName.trim())}
            pending={createOrg.isPending}
          />
        </Column>

        <Column title="Workspaces">
          {!orgId && <EmptyHint text="Select an organization" />}
          {workspacesQuery.data?.map((workspace) => (
            <ListItem
              key={workspace.id}
              label={workspace.name}
              selected={workspace.id === workspaceId}
              onClick={() => setSearchParams({ org: orgId!, workspace: workspace.id })}
            />
          ))}
          {orgId && (
            <CreateForm
              placeholder="New workspace name"
              value={newWorkspaceName}
              onChange={setNewWorkspaceName}
              onSubmit={() =>
                newWorkspaceName.trim() && createWorkspace.mutate(newWorkspaceName.trim())
              }
              pending={createWorkspace.isPending}
            />
          )}
        </Column>

        <Column title="Projects">
          {!workspaceId && <EmptyHint text="Select a workspace" />}
          {projectsQuery.data?.map((project) => (
            <ListItem
              key={project.id}
              label={project.name}
              onClick={() => navigate(`/projects/${project.id}`)}
            />
          ))}
          {workspaceId && (
            <CreateForm
              placeholder="New project name"
              value={newProjectName}
              onChange={setNewProjectName}
              onSubmit={() =>
                newProjectName.trim() && createProject.mutate(newProjectName.trim())
              }
              pending={createProject.isPending}
            />
          )}
        </Column>
      </div>
    </Layout>
  )
}

function Column({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold text-gray-500 uppercase">{title}</h2>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

function ListItem({
  label,
  selected,
  onClick,
}: {
  label: string
  selected?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`block w-full rounded-lg px-3 py-2 text-left text-sm ${
        selected ? 'bg-brand-50 font-medium text-brand-700' : 'text-gray-700 hover:bg-gray-50'
      }`}
    >
      {label}
    </button>
  )
}

function EmptyHint({ text }: { text: string }) {
  return <p className="px-3 py-2 text-sm text-gray-400">{text}</p>
}

function CreateForm({
  placeholder,
  value,
  onChange,
  onSubmit,
  pending,
}: {
  placeholder: string
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  pending: boolean
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
      className="mt-2 flex gap-2 border-t border-gray-100 pt-2"
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
      />
      <button
        type="submit"
        disabled={pending || !value.trim()}
        className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
      >
        Add
      </button>
    </form>
  )
}
