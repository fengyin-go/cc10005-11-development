/** 隔离处置流转接口封装：所有写动作都带 values 载荷，返回统一 ActionResult。 */
import { fetchJson, request } from '@/api/client'

import type {
  ActionResult,
  NodeMeta,
  NodeStats,
  PageResult,
  QuarantineSample,
} from './types'

const BASE = '/api/validator/quarantine'

export function fetchNodeMeta(): Promise<NodeMeta> {
  return fetchJson<NodeMeta>(`${BASE}/nodes`)
}

export function fetchNodeStats(): Promise<NodeStats> {
  return fetchJson<NodeStats>(`${BASE}/stats`)
}

export async function fetchSamples(params: {
  node?: string
  keyword?: string
  page?: number
  size?: number
}): Promise<PageResult<QuarantineSample>> {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  return fetchJson<PageResult<QuarantineSample>>(`${BASE}/samples?${query.toString()}`)
}

export function fetchSample(id: number): Promise<QuarantineSample> {
  return fetchJson<QuarantineSample>(`${BASE}/samples/${id}`)
}

async function postAction(
  id: number,
  action: string,
  values: Record<string, unknown>,
): Promise<ActionResult> {
  const response = await request(`${BASE}/samples/${id}/${action}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: '接口返回异常' }))
    throw new Error(detail.detail ?? `接口返回 ${response.status}`)
  }
  return response.json()
}

export const correctSample = (id: number, candidateValue: string, operator: string) =>
  postAction(id, 'correct', { candidate_value: candidateValue, operator })

export const revalidateSample = (
  id: number,
  payload: { result?: '通过' | '警告' | '阻断'; hits?: Array<{ expression: string; level: '通过' | '警告' | '阻断'; message: string }> },
) => postAction(id, 'revalidate', payload)

export const authorizeSample = (id: number, operator: string) =>
  postAction(id, 'authorize', { operator })

export const deliverSample = (id: number, targetSystem: string, operator: string) =>
  postAction(id, 'deliver', { target_system: targetSystem, operator })

export const trialRule = (id: number, ruleVersion: string, operator: string) =>
  postAction(id, 'trial', { rule_version: ruleVersion, operator })

export const abandonSample = (id: number, reason: string) =>
  postAction(id, 'abandon', { reason })
