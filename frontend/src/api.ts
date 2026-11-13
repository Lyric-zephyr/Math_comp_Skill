export type Settings = { subject: string; ai: string; run_mode: string; model: string; mode: string; chapter: string; output_format: string; pdf_engine: string }
export type Options = { subjects: string[]; providers: Record<string, string[]>; modules: string[]; subject_modules: Record<string, string[]>; batch_counts: Record<string, Record<string, number>>; defaults: Settings; api_defaults: Record<string, string>; configured: Record<string, boolean>; cli_models: string[] }
export type Artifact = { id: string; name: string; kind: string; chapter: string }
export type Job = { id: string; kind: string; status: string; percent: number; stage: string; successes: number; failures: number; modules: Record<string, string>; logs: string[]; artifacts: Artifact[]; sequence: number }
export const terminal = (job: Job | null) => !job || ['succeeded', 'partial', 'failed'].includes(job.status)
export async function api<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  const response = await fetch(`/api/${path}`, body === undefined ? {} : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const result = await response.json()
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '请求无效，请检查输入')
  return result
}
