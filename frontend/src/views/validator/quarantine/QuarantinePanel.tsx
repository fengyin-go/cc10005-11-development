/** 隔离处置流转面板：流转图 + 样本列表 + 详情抽屉。 */
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  fetchNodeMeta,
  fetchNodeStats,
  fetchSample,
  fetchSamples,
} from './api'
import FlowDiagram from './FlowDiagram'
import SampleDetail from './SampleDetail'
import type {
  NodeMeta,
  NodeName,
  NodeStats,
  QuarantineSample,
} from './types'

const OPERATOR = '值班管理员'

const TABLE_COLUMNS = [
  '样本编号',
  '数据集',
  '字段',
  '原值',
  '候选值',
  '活动规则版本',
  '当前节点',
  '阻断/警告',
  '尝试次数',
  '授权',
  '回执',
] as const

export default function QuarantinePanel() {
  const [meta, setMeta] = useState<NodeMeta>({ node_order: [], active_nodes: [], terminal_nodes: [] })
  const [stats, setStats] = useState<NodeStats>({})
  const [samples, setSamples] = useState<QuarantineSample[]>([])
  const [total, setTotal] = useState(0)
  const [nodeFilter, setNodeFilter] = useState<NodeName | ''>('')
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<QuarantineSample | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [loading, setLoading] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const [metaData, statsData, pageData] = await Promise.all([
        fetchNodeMeta(),
        fetchNodeStats(),
        fetchSamples({ node: nodeFilter || undefined, keyword: keyword || undefined, size: 100 }),
      ])
      setMeta(metaData)
      setStats(statsData)
      setSamples(pageData.items)
      setTotal(pageData.total)
    } catch (error) {
      setMessage({ ok: false, text: error instanceof Error ? error.message : '隔离流转数据读取失败' })
    } finally {
      setLoading(false)
    }
  }, [nodeFilter, keyword])

  useEffect(() => {
    void reload()
  }, [reload])

  const nodeOptions = useMemo(() => meta.node_order, [meta])

  async function openSample(id: number) {
    try {
      const detail = await fetchSample(id)
      setSelected(detail)
    } catch (error) {
      setMessage({ ok: false, text: error instanceof Error ? error.message : '样本详情读取失败' })
    }
  }

  async function handleChanged(text: string, ok: boolean) {
    setMessage({ ok, text })
    if (ok && selected) {
      try {
        const refreshed = await fetchSample(selected.id)
        setSelected(refreshed)
      } catch {
        setSelected(null)
      }
    }
    await reload()
  }

  return (
    <section className="quarantine-panel">
      <header className="quarantine-head">
        <div>
          <h3>隔离处置流转</h3>
          <p className="page-desc">
            样本带原值与规则版本进入隔离节点，修正候选值后逐次独立重验；只有重验通过才能申请分发授权，
            授权与交付回执全链路留痕。
          </p>
        </div>
      </header>

      <FlowDiagram
        nodeOrder={meta.node_order}
        stats={stats}
        currentNode={selected?.current_node}
        onNodeClick={(node) => setNodeFilter((prev) => (prev === node ? '' : node))}
      />

      <div className="filter-bar quarantine-filter">
        <label className="filter-item">
          <span>节点过滤（点击流转图节点同样可过滤）</span>
          <select value={nodeFilter} onChange={(e) => setNodeFilter(e.target.value as NodeName | '')}>
            <option value="">全部节点</option>
            {nodeOptions.map((node) => (
              <option key={node} value={node}>{node}（{stats[node] ?? 0}）</option>
            ))}
          </select>
        </label>
        <label className="filter-item">
          <span>样本编号 / 数据集</span>
          <input value={keyword} placeholder="按编号或数据集检索" onChange={(e) => setKeyword(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={() => void reload()}>查询</button>
        <button type="button" className="btn ghost" onClick={() => { setNodeFilter(''); setKeyword('') }}>
          重置条件
        </button>
      </div>

      <table className="data-table quarantine-table">
        <thead>
          <tr>
            {TABLE_COLUMNS.map((column) => <th key={column}>{column}</th>)}
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {samples.map((sample) => {
            const blockers = sample.hits.filter((hit) => hit.level === '阻断')
            const warners = sample.hits.filter((hit) => hit.level === '警告')
            return (
              <tr key={sample.id} className={sample.current_node === '已放弃' ? 'row-abandoned' : ''}>
                <td>{sample.sample_code}</td>
                <td>{sample.dataset}</td>
                <td>{sample.field_name}</td>
                <td className="original-value">{sample.original_value}</td>
                <td>{sample.candidate_value ?? '—'}</td>
                <td>
                  {sample.active_rule_version}
                  {sample.rule_version_history.length > 0 && (
                    <span className="version-switched" title="发生过规则版本切换试验">↺{sample.rule_version_history.length}</span>
                  )}
                </td>
                <td>
                  <span className={`node-pill ${sample.current_node === '已交付' || sample.current_node === '已放弃' ? 'terminal' : ''}`}>
                    {sample.current_node}
                  </span>
                </td>
                <td>
                  <span className="hit-summary">
                    <span className="level-badge is-block">阻断 {blockers.length}</span>
                    <span className="level-badge is-warn">警告 {warners.length}</span>
                  </span>
                </td>
                <td>{sample.attempts.length}</td>
                <td>{sample.authorization ? sample.authorization.auth_code : '—'}</td>
                <td>
                  {sample.receipt ? (
                    <button type="button" className="link" onClick={() => void openSample(sample.id)}>
                      {sample.receipt.receipt_code}
                    </button>
                  ) : '—'}
                </td>
                <td className="row-actions">
                  <button type="button" className="link" onClick={() => void openSample(sample.id)}>
                    查看流转
                  </button>
                </td>
              </tr>
            )
          })}
          {samples.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={TABLE_COLUMNS.length + 1}>
                {loading ? '加载中…' : '该节点下暂无隔离样本'}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条隔离样本{nodeFilter ? ` · 当前过滤：${nodeFilter}` : ''}</span>
        {message && (
          <span className={message.ok ? 'ok-text' : 'error-text'}>
            {message.text}
            <button type="button" className="link message-dismiss" onClick={() => setMessage(null)}>知道了</button>
          </span>
        )}
      </footer>

      {selected && (
        <SampleDetail
          sample={selected}
          operator={OPERATOR}
          onClose={() => setSelected(null)}
          onChanged={handleChanged}
        />
      )}
    </section>
  )
}
