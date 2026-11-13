/** 样本详情抽屉：完整流转证据 + 按当前节点启用的处置动作。 */
import { useState } from 'react'

import {
  abandonSample,
  authorizeSample,
  correctSample,
  deliverSample,
  revalidateSample,
  trialRule,
} from './api'
import type { QuarantineSample, RuleHit } from './types'

interface SampleDetailProps {
  sample: QuarantineSample
  operator: string
  onClose: () => void
  onChanged: (message: string, ok: boolean) => void
}

const LEVEL_CLASS: Record<string, string> = {
  阻断: 'is-block',
  警告: 'is-warn',
  通过: 'is-pass',
}

const ATTEMPT_CLASS: Record<string, string> = {
  待重验: 'attempt-pending',
  重验通过: 'attempt-passed',
  重验驳回: 'attempt-rejected',
  已被新尝试取代: 'attempt-stale',
}

export default function SampleDetail({ sample, operator, onClose, onChanged }: SampleDetailProps) {
  const [candidate, setCandidate] = useState(sample.candidate_value ?? '')
  const [ruleVersion, setRuleVersion] = useState('')
  const [targetSystem, setTargetSystem] = useState('数据仓库主通道')
  const [abandonReason, setAbandonReason] = useState('')
  const [busy, setBusy] = useState(false)

  const isTerminal = sample.current_node === '已交付' || sample.current_node === '已放弃'
  const atQuarantine = sample.current_node === '隔离节点'
  const atRevalidate = sample.current_node === '重验节点'
  const atAuthorize = sample.current_node === '分发授权节点'

  async function run(
    task: () => Promise<{ ok: boolean; message: string }>,
  ) {
    if (busy) return
    setBusy(true)
    try {
      const result = await task()
      onChanged(result.message, result.ok)
    } catch (error) {
      onChanged(error instanceof Error ? error.message : '操作失败', false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="drawer-mask" role="presentation" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label="样本流转详情" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <div>
            <h3>{sample.sample_code}</h3>
            <p className="drawer-sub">
              {sample.dataset} · 字段 {sample.field_name} · 规则 {sample.rule_code}
              <span className={`node-pill ${isTerminal ? 'terminal' : ''}`}>{sample.current_node}</span>
            </p>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>关闭</button>
        </header>

        <div className="drawer-body">
          <section className="detail-card">
            <h4>进入隔离时的样本快照</h4>
            <dl className="detail-grid">
              <div><dt>原值</dt><dd className="original-value">{sample.original_value}</dd></div>
              <div><dt>当前候选值</dt><dd>{sample.candidate_value ?? '尚未修正'}</dd></div>
              <div><dt>活动规则版本</dt><dd>{sample.active_rule_version}</dd></div>
              <div><dt>最近更新</dt><dd>{sample.updated_at}</dd></div>
            </dl>
            {sample.rule_version_history.length > 0 && (
              <p className="version-hint">
                规则版本轨迹：
                {sample.rule_version_history.map((change) => `${change.version}（${change.left_at} 离开）`).join(' → ')}
                → {sample.active_rule_version}
              </p>
            )}
            <p className="stuck-reason">
              <strong>为何停在此节点：</strong>{sample.stuck_reason}
            </p>
          </section>

          <section className="detail-card">
            <h4>表达式命中（{sample.hits.length}）</h4>
            <ul className="hit-list">
              {sample.hits.map((hit: RuleHit) => (
                <li key={hit.expression} className="hit-item">
                  <span className={`level-badge ${LEVEL_CLASS[hit.level] ?? ''}`}>{hit.level}者</span>
                  <div>
                    <code>{hit.expression}</code>
                    <p>{hit.message}</p>
                  </div>
                </li>
              ))}
              {sample.hits.length === 0 && <li className="empty-state">暂无隔离时命中记录</li>}
            </ul>
          </section>

          <section className="detail-card">
            <h4>重验尝试（每次修正生成独立尝试，共 {sample.attempts.length} 次）</h4>
            <ol className="attempt-list">
              {sample.attempts.map((attempt) => (
                <li key={attempt.attempt_id} className={`attempt-item ${ATTEMPT_CLASS[attempt.status] ?? ''}`}>
                  <div className="attempt-head">
                    <strong>{attempt.attempt_id}</strong>
                    <span className="attempt-status">{attempt.status}</span>
                  </div>
                  <p className="attempt-meta">
                    规则版本 {attempt.rule_version} · 候选值 {attempt.candidate_value ?? '—'} · 处置者 {attempt.operator}
                  </p>
                  <p className="attempt-meta">提交 {attempt.created_at}{attempt.decided_at ? ` · 结论 ${attempt.decided_at}` : ''}</p>
                  {attempt.hits.length > 0 && (
                    <div className="attempt-hits">
                      {attempt.hits.map((hit) => (
                        <span key={hit.expression} className={`level-badge ${LEVEL_CLASS[hit.level] ?? ''}`}>
                          {hit.level}：{hit.expression}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="attempt-note">{attempt.note}</p>
                </li>
              ))}
              {sample.attempts.length === 0 && <li className="empty-state">还没有重验尝试，先在下方修正候选值</li>}
            </ol>
          </section>

          {sample.authorization && (
            <section className="detail-card">
              <h4>分发授权（同一样本最多一份）</h4>
              <dl className="detail-grid">
                <div><dt>授权号</dt><dd>{sample.authorization.auth_code}</dd></div>
                <div><dt>取得者</dt><dd>{sample.authorization.granted_to}</dd></div>
                <div><dt>签发时间</dt><dd>{sample.authorization.granted_at}</dd></div>
                <div><dt>依据尝试</dt><dd>{sample.authorization.based_on_attempt}</dd></div>
              </dl>
            </section>
          )}

          {sample.receipt && (
            <section className="detail-card receipt-card">
              <h4>实际交付回执</h4>
              <dl className="detail-grid">
                <div><dt>回执编号</dt><dd>{sample.receipt.receipt_code}</dd></div>
                <div><dt>交付时间</dt><dd>{sample.receipt.delivered_at}</dd></div>
                <div><dt>目标系统</dt><dd>{sample.receipt.target_system}</dd></div>
                <div><dt>交付操作人</dt><dd>{sample.receipt.operator}</dd></div>
                <div><dt>冻结规则版本</dt><dd>{sample.receipt.rule_version_frozen}</dd></div>
                <div><dt>冻结原值</dt><dd>{sample.receipt.original_value_frozen}</dd></div>
                <div><dt>冻结候选值</dt><dd>{sample.receipt.candidate_value_frozen}</dd></div>
                <div><dt>冻结尝试</dt><dd>{sample.receipt.attempt_id_frozen}</dd></div>
              </dl>
              <p className="receipt-hint">证据已随交付冻结，新版规则试验不会改写这份回执。</p>
            </section>
          )}

          {sample.current_node === '已放弃' && (
            <section className="detail-card abandon-card">
              <h4>放弃记录（终点）</h4>
              <p className="attempt-meta">放弃时间：{sample.abandoned_at}</p>
              <p className="attempt-note">{sample.abandon_reason}</p>
            </section>
          )}

          {!isTerminal && (
            <section className="detail-card action-card">
              <h4>处置动作</h4>

              {(atQuarantine || atRevalidate) && (
                <div className="action-row">
                  <label className="action-field">
                    <span>修正候选值并送往重验（生成新尝试）</span>
                    <input value={candidate} onChange={(e) => setCandidate(e.target.value)} placeholder="输入修正后的候选值" />
                  </label>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={busy || !candidate.trim()}
                    onClick={() => run(() => correctSample(sample.id, candidate.trim(), operator))}
                  >
                    修正并重验
                  </button>
                </div>
              )}

              {atRevalidate && (
                <div className="action-row">
                  <span className="action-field"><span>提交当前尝试的重验结论</span></span>
                  <div className="btn-group">
                    <button type="button" className="btn" disabled={busy} onClick={() => run(() => revalidateSample(sample.id, { result: '通过' }))}>
                      重验通过
                    </button>
                    <button type="button" className="btn" disabled={busy} onClick={() => run(() => revalidateSample(sample.id, { result: '警告' }))}>
                      仅警告（放行留痕）
                    </button>
                    <button type="button" className="btn danger" disabled={busy} onClick={() => run(() => revalidateSample(sample.id, { result: '阻断' }))}>
                      阻断驳回
                    </button>
                  </div>
                </div>
              )}

              {atAuthorize && (
                <>
                  <div className="action-row">
                    <label className="action-field">
                      <span>申请分发资格（以「{operator}」名义）</span>
                      <input value={operator} readOnly />
                    </label>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={busy || Boolean(sample.authorization)}
                      onClick={() => run(() => authorizeSample(sample.id, operator))}
                    >
                      {sample.authorization ? '授权已签发' : '申请授权'}
                    </button>
                  </div>
                  <div className="action-row">
                    <label className="action-field">
                      <span>数据分发模块确认交付</span>
                      <input value={targetSystem} onChange={(e) => setTargetSystem(e.target.value)} placeholder="目标系统" />
                    </label>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={busy || !sample.authorization || !targetSystem.trim()}
                      title={sample.authorization ? '凭授权生成交付回执' : '需要先取得分发授权'}
                      onClick={() => run(() => deliverSample(sample.id, targetSystem.trim(), operator))}
                    >
                      确认交付
                    </button>
                  </div>
                </>
              )}

              <div className="action-row">
                <label className="action-field">
                  <span>切换新版规则试验（已交付数据保持原证据，试验成功需重新申请资格）</span>
                  <input value={ruleVersion} onChange={(e) => setRuleVersion(e.target.value)} placeholder="新版规则版本号，如 v4" />
                </label>
                <button
                  type="button"
                  className="btn"
                  disabled={busy || !ruleVersion.trim() || ruleVersion.trim() === sample.active_rule_version}
                  onClick={() => run(() => trialRule(sample.id, ruleVersion.trim(), operator))}
                >
                  切换试验
                </button>
              </div>

              <div className="action-row">
                <label className="action-field">
                  <span>放弃样本（放弃即终点，迟到的通过结果不能重新放行）</span>
                  <input value={abandonReason} onChange={(e) => setAbandonReason(e.target.value)} placeholder="放弃原因" />
                </label>
                <button
                  type="button"
                  className="btn danger"
                  disabled={busy}
                  onClick={() => run(() => abandonSample(sample.id, abandonReason.trim()))}
                >
                  放弃样本
                </button>
              </div>
            </section>
          )}
        </div>
      </aside>
    </div>
  )
}
