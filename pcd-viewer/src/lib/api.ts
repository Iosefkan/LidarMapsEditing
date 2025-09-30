export type FileRecord = {
  id: string
  filename: string
  size?: number
  created_at: string
  original_url?: string | null
  cleaned_url?: string | null
  delta_url?: string | null
  summary?: Record<string, any> | null
}

export type CleanParams = {
  grid?: number
  q_low?: number
  q_high?: number
  smooth_cells?: number
  h_min?: number
  h_max?: number
  min_len?: number
  min_width?: number
  max_width?: number
  min_elong?: number
  density_min?: number
  use_hough?: boolean
  hough_theta_step?: number
  hough_rho_bin?: number
  hough_topk?: number
  hough_min_len?: number
  hough_min_w?: number
  hough_max_w?: number
  hough_dilate?: number
  debug_dump?: boolean
}

const API = '/api'

export async function apiUploadPCD(file: File): Promise<FileRecord> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API}/upload`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(await res.text())
  return await res.json()
}

export async function apiListFiles(): Promise<FileRecord[]> {
  const res = await fetch(`${API}/files`)
  if (!res.ok) throw new Error(await res.text())
  return await res.json()
}

export async function apiGetFile(id: string): Promise<FileRecord> {
  const res = await fetch(`${API}/files/${id}`)
  if (!res.ok) throw new Error(await res.text())
  return await res.json()
}

export async function apiClean(id: string, params: CleanParams): Promise<FileRecord & { summary?: any }>{
  const res = await fetch(`${API}/files/${id}/clean`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params ?? {})
  })
  if (!res.ok) throw new Error(await res.text())
  const data = await res.json()
  // normalize to FileRecord shape
  return {
    id: data.id,
    filename: '',
    created_at: '',
    original_url: data.original_url,
    cleaned_url: data.cleaned_url,
    delta_url: data.delta_url,
    summary: data.summary
  }
}

export async function apiDeleteFile(id: string): Promise<void> {
  const res = await fetch(`${API}/files/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function apiSaveOriginal(id: string, file: Blob, filename = 'original.pcd'): Promise<FileRecord> {
  const fd = new FormData()
  fd.append('file', file, filename)
  const res = await fetch(`${API}/files/${id}/save_original`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(await res.text())
  return await res.json()
}

export async function apiSaveCleaned(id: string, file: Blob, filename = 'cleaned.pcd'): Promise<FileRecord> {
  const fd = new FormData()
  fd.append('file', file, filename)
  const res = await fetch(`${API}/files/${id}/save_cleaned`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(await res.text())
  return await res.json()
}


