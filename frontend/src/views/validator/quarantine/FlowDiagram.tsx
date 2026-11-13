/** 隔离处置流转图：隔离 → 重验 → 分发授权 → 已交付；放弃为独立终点。

 * 图上需要同时表达：
 * - 每个节点的在留样本数与当前样本所处位置；
 * - 边的放行/驳回条件（阻断退回、警告不阻断、按严格者决定出口）；
 * - 放弃是终点，迟到的通过结果不能重新放行。
 */
import type { NodeName, NodeStats } from './types'

const MAIN_NODES: NodeName[] = ['隔离节点', '重验节点', '分发授权节点', '已交付']
const ABANDON_NODE: NodeName = '已放弃'

const EDGE_LABELS: Record<string, string> = {
  '隔离节点->重验节点': '修正候选值\n生成独立尝试',
  '重验节点->隔离节点': '阻断者驳回，退回修正',
  '重验节点->分发授权节点': '通过放行（警告不阻断，按严格者定出口）',
  '分发授权节点->已交付': '凭唯一授权交付，回执冻结证据',
  '分发授权节点->已放弃': '处置者放弃',
}

interface FlowDiagramProps {
  nodeOrder: NodeName[]
  stats?: NodeStats
  currentNode?: NodeName
  onNodeClick?: (node: NodeName) => void
}

export default function FlowDiagram({ nodeOrder, stats, currentNode, onNodeClick }: FlowDiagramProps) {
  const nodes = nodeOrder.length > 0 ? nodeOrder : [...MAIN_NODES, ABANDON_NODE]
  const main = nodes.filter((node) => node !== ABANDON_NODE)

  return (
    <div className="flow-scroll">
      <div className="flow-canvas">
        <div className="flow-main">
          {main.map((node, index) => {
            const isActive = node === currentNode
            const isTerminal = node === '已交付'
            const count = stats?.[node] ?? 0
            return (
              <div className="flow-step" key={node}>
                {index > 0 && (
                  <Edge
                    label={EDGE_LABELS[`${main[index - 1]}->${node}`] ?? ''}
                    tone={node === '隔离节点' ? 'danger' : 'normal'}
                  />
                )}
                <button
                  type="button"
                  className={`flow-node ${isActive ? 'is-active' : ''} ${isTerminal ? 'is-terminal' : ''}`}
                  onClick={() => onNodeClick?.(node)}
                  title={onNodeClick ? `点击只看「${node}」的样本` : undefined}
                >
                  <span className="flow-node-name">{node}</span>
                  <span className="flow-node-meta">
                    {isTerminal ? '终点 · 证据冻结' : '在留样本'}
                    <strong>{count}</strong>
                  </span>
                  {isActive && <span className="flow-node-flag">当前位置</span>}
                </button>
              </div>
            )
          })}
        </div>

        <div className="flow-return">
          <span className="flow-return-spacer" />
          <div className="flow-edge danger return-edge">
            <span className="flow-edge-line" />
            <span className="flow-edge-label">{EDGE_LABELS['重验节点->隔离节点']}</span>
          </div>
          <span className="flow-return-spacer wide" />
        </div>

        <div className="flow-branch">
          <Edge label={EDGE_LABELS['分发授权节点->已放弃']} tone="muted" vertical />
          <button
            type="button"
            className={`flow-node is-terminal abandon ${currentNode === ABANDON_NODE ? 'is-active' : ''}`}
            onClick={() => onNodeClick?.(ABANDON_NODE)}
            title={onNodeClick ? '点击只看「已放弃」的样本' : undefined}
          >
            <span className="flow-node-name">{ABANDON_NODE}</span>
            <span className="flow-node-meta">
              终点 · 不再放行
              <strong>{stats?.[ABANDON_NODE] ?? 0}</strong>
            </span>
            {currentNode === ABANDON_NODE && <span className="flow-node-flag">当前位置</span>}
          </button>
        </div>

        <div className="flow-legend">
          <span><i className="dot block" />阻断者：决定出口，驳回回隔离</span>
          <span><i className="dot warn" />警告者：留痕不阻断</span>
          <span className="flow-legend-hint">多表达式同时命中时，按最严格者决定出口</span>
        </div>
      </div>
    </div>
  )
}

function Edge({ label, tone, vertical }: { label: string; tone: 'normal' | 'danger' | 'muted'; vertical?: boolean }) {
  return (
    <div className={`flow-edge ${tone} ${vertical ? 'vertical' : ''}`}>
      <span className="flow-edge-line" />
      {label && (
        <span className="flow-edge-label">
          {label.split('\n').map((line) => (
            <span key={line} className="flow-edge-label-line">{line}</span>
          ))}
        </span>
      )}
    </div>
  )
}
