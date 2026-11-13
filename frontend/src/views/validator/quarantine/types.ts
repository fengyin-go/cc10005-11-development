/** 隔离处置流转的接口类型，字段与后端 QuarantineService 保持一致。 */

export type NodeName = '隔离节点' | '重验节点' | '分发授权节点' | '已交付' | '已放弃'

export type HitLevel = '通过' | '警告' | '阻断'

export interface RuleHit {
  expression: string
  level: HitLevel
  message: string
}

export type AttemptStatus = '待重验' | '重验通过' | '重验驳回' | '已被新尝试取代'

export interface Attempt {
  attempt_id: string
  attempt_no: number
  rule_version: string
  candidate_value: string | null
  operator: string
  status: AttemptStatus
  created_at: string
  decided_at: string | null
  hits: RuleHit[]
  note: string
}

export interface Authorization {
  auth_code: string
  granted_to: string
  granted_at: string
  based_on_attempt: string | null
  rule_version: string
  revoked: boolean
  revoke_reason?: string
}

export interface DeliveryReceipt {
  receipt_code: string
  delivered_at: string
  target_system: string
  operator: string
  auth_code: string
  rule_version_frozen: string
  original_value_frozen: string
  candidate_value_frozen: string
  attempt_id_frozen: string | null
}

export interface RuleVersionChange {
  version: string
  left_at: string
  reason: string
}

export interface QuarantineSample {
  id: number
  sample_code: string
  dataset: string
  field_name: string
  original_value: string
  candidate_value: string | null
  rule_code: string
  active_rule_version: string
  current_node: NodeName
  hits: RuleHit[]
  attempts: Attempt[]
  authorization: Authorization | null
  receipt: DeliveryReceipt | null
  rule_version_history: RuleVersionChange[]
  created_at: string
  updated_at: string
  delivered_at?: string | null
  abandoned_at?: string | null
  abandon_reason?: string
  stuck_reason?: string
  pending: boolean
  abnormal: boolean
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface ActionResult {
  ok: boolean
  message: string
  entry: QuarantineSample | null
}

export interface NodeMeta {
  node_order: NodeName[]
  active_nodes: NodeName[]
  terminal_nodes: NodeName[]
}

export type NodeStats = Record<string, number>
