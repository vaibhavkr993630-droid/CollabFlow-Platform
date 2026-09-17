import { apiClient } from './client'
import type { Attachment } from '../types'

export async function listAttachments(taskId: string): Promise<Attachment[]> {
  const { data } = await apiClient.get<Attachment[]>(`/api/tasks/${taskId}/attachments`)
  return data
}

export async function uploadAttachment(taskId: string, file: File): Promise<Attachment> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<Attachment>(
    `/api/tasks/${taskId}/attachments`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

export async function getDownloadUrl(taskId: string, attachmentId: string): Promise<string> {
  const { data } = await apiClient.get<{ download_url: string }>(
    `/api/tasks/${taskId}/attachments/${attachmentId}/download`,
  )
  return data.download_url
}

export async function deleteAttachment(taskId: string, attachmentId: string): Promise<void> {
  await apiClient.delete(`/api/tasks/${taskId}/attachments/${attachmentId}`)
}
