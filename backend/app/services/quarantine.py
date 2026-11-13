"""隔离处置流转业务规则。

样本进入隔离节点后，只有“修正 → 重验 → 分发授权 → 交付”这一条正向通路，
本模块把所有节点流转约束、尝试版本核对与授权互斥都收在一处，保证：

1. 每次重验生成独立尝试；旧尝试迟到的放行请求要核对当前节点，不能越过校验。
2. 多条表达式同时命中时，阻断级别按最严格者决定出口，并区分阻断者与警告者。
3. 分发授权对同一样本最多签发一份，两名处置者争同一出口时后者被拒。
4. 放弃样本即终点；已交付样本的证据（规则版本、回执）冻结，不被新版规则改写。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "quarantine_sample"

# 流转节点：前三个是活动节点，后两个是终点
NODE_QUARANTINE = "隔离节点"
NODE_REVALIDATE = "重验节点"
NODE_AUTHORIZE = "分发授权节点"
NODE_DELIVERED = "已交付"
NODE_ABANDONED = "已放弃"
ACTIVE_NODES = [NODE_QUARANTINE, NODE_REVALIDATE, NODE_AUTHORIZE]
TERMINAL_NODES = [NODE_DELIVERED, NODE_ABANDONED]
NODE_ORDER = [NODE_QUARANTINE, NODE_REVALIDATE, NODE_AUTHORIZE, NODE_DELIVERED]

# 阻断级别严格度：数字越大越严格，出口由最严格者决定
LEVEL_PASS = "通过"
LEVEL_WARN = "警告"
LEVEL_BLOCK = "阻断"
LEVEL_RANK = {LEVEL_PASS: 0, LEVEL_WARN: 1, LEVEL_BLOCK: 2}

# 尝试状态
ATTEMPT_PENDING = "待重验"
ATTEMPT_PASSED = "重验通过"
ATTEMPT_REJECTED = "重验驳回"
ATTEMPT_STALE = "已被新尝试取代"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class QuarantineService:
    """隔离样本状态机。所有写操作都返回 (数据, 消息)，由路由层决定 HTTP 语义。"""

    # ---------- 查询 ----------
    def list_samples(
        self,
        *,
        node: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if node:
            rows = [row for row in rows if row.get("current_node") == node]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("sample_code", ""))
                or keyword in str(row.get("dataset", ""))
            ]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_sample(self, sample_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, sample_id)

    def stats(self) -> dict[str, int]:
        rows = store.rows(MODULE)
        result = {node: 0 for node in ACTIVE_NODES + TERMINAL_NODES}
        for row in rows:
            node = str(row.get("current_node", ""))
            result[node] = result.get(node, 0) + 1
        result["隔离样本总数"] = len(rows)
        return result

    def stuck_reason(self, sample: dict[str, Any]) -> str:
        """说明样本为什么仍停留在当前节点；已到终点的样本给出终态说明。"""
        node = sample.get("current_node")
        if node == NODE_DELIVERED:
            return "样本已交付，证据已冻结，不再参与流转。"
        if node == NODE_ABANDONED:
            return f"样本已于 {sample.get('abandoned_at')} 放弃，放弃是终点，迟到的通过结果也不能重新放行。"
        if node == NODE_QUARANTINE:
            blocker = self._strictest_hit(sample.get("hits", []))
            if blocker and blocker.get("level") == LEVEL_BLOCK:
                return (
                    f"仍在隔离：表达式「{blocker.get('expression')}」命中阻断，"
                    "处置者尚未提交修正后的候选值。"
                )
            return "仍在隔离：等待处置者修正候选值并发起重验。"
        if node == NODE_REVALIDATE:
            attempt = self._latest_attempt(sample)
            if attempt and attempt.get("status") == ATTEMPT_PENDING:
                return f"停在重验节点：尝试 {attempt.get('attempt_no')} 已提交，等待重验结论。"
            return "停在重验节点：上一轮重验未通过，需修正后重新发起。"
        if node == NODE_AUTHORIZE:
            if sample.get("authorization"):
                return "已取得分发授权，等待数据分发模块确认交付回执。"
            return "重验已通过，等待处置者申请分发资格；同一出口最多只签发一份授权。"
        return "节点状态未知。"

    # ---------- 写操作 ----------
    def correct(self, sample_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """处置者修正候选值并送往重验节点：每次都生成一条独立尝试。"""
        sample = self.get_sample(sample_id)
        if sample is None:
            return None, f"隔离样本 {sample_id} 不存在或已归档"
        node = sample.get("current_node")
        if node in TERMINAL_NODES:
            return None, f"样本已处于「{node}」终点，不能再修正或重验"
        if node not in (NODE_QUARANTINE, NODE_REVALIDATE):
            return None, f"样本当前在「{node}」，只有隔离/重验节点允许修正候选值"

        candidate = str(values.get("candidate_value") or "").strip()
        operator = str(values.get("operator") or "值班管理员").strip()
        if not candidate:
            return None, "候选值不能为空：修正后的值是送往重验节点的依据"

        # 旧尝试一律标记为被取代，其迟到结果不能再推动当前样本
        for attempt in sample.get("attempts", []):
            if attempt.get("status") == ATTEMPT_PENDING:
                attempt["status"] = ATTEMPT_STALE
                attempt["note"] = "处置者发起了新一轮修正，本尝试不再代表当前样本"

        sample["candidate_value"] = candidate
        attempt_no = len(sample.get("attempts", [])) + 1
        attempt = {
            "attempt_id": f"{sample['sample_code']}-A{attempt_no:02d}",
            "attempt_no": attempt_no,
            "rule_version": sample.get("active_rule_version"),
            "candidate_value": candidate,
            "operator": operator,
            "status": ATTEMPT_PENDING,
            "created_at": _now(),
            "decided_at": None,
            "hits": [],
            "note": "候选值已送入重验节点，等待结论",
        }
        sample.setdefault("attempts", []).append(attempt)
        sample["current_node"] = NODE_REVALIDATE
        sample["updated_at"] = _now()
        # 新一轮重验会让旧的分发资格失效：重验中的样本不能越过校验
        sample["authorization"] = None
        return sample, f"候选值已修正并生成独立尝试 {attempt['attempt_id']}，样本进入重验节点"

    def submit_revalidation(
        self, sample_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """重验节点给出结论。

        结论可以由调用方带 hits（含阻断/警告级别）驱动；若只给 result 则按结果造一条命中。
        关键不变量：只受理“当前节点仍在重验、且尝试仍是最新有效尝试”的请求，
        旧尝试迟到的放行请求会被核对拦下，样本停在原地。
        """
        sample = self.get_sample(sample_id)
        if sample is None:
            return None, f"隔离样本 {sample_id} 不存在或已归档"
        if sample.get("current_node") in TERMINAL_NODES:
            return None, f"样本已到「{sample.get('current_node')}」终点，迟到的重验结果不再受理"
        if sample.get("current_node") != NODE_REVALIDATE:
            return None, (
                f"核对当前节点失败：样本当前在「{sample.get('current_node')}」而非重验节点，"
                "旧尝试的放行请求不能越过校验"
            )

        attempt = self._latest_attempt(sample)
        if attempt is None or attempt.get("status") != ATTEMPT_PENDING:
            return None, "没有等待结论的有效尝试，可能已被新一轮修正取代"

        attempt_id = values.get("attempt_id")
        if attempt_id and str(attempt_id) != str(attempt["attempt_id"]):
            return None, (
                f"尝试 {attempt_id} 已不是当前有效尝试（当前为 {attempt['attempt_id']}），"
                "迟到的放行请求被拒绝，样本保持在重验节点"
            )

        hits = self._normalize_hits(values.get("hits"), values.get("result"))
        strictest = self._strictest_hit(hits)
        attempt["hits"] = hits
        attempt["decided_at"] = _now()

        if strictest is None or strictest.get("level") == LEVEL_PASS:
            attempt["status"] = ATTEMPT_PASSED
            attempt["note"] = "重验通过，样本可前往分发授权节点"
            sample["current_node"] = NODE_AUTHORIZE
            sample["updated_at"] = _now()
            return sample, f"尝试 {attempt['attempt_id']} 重验通过，样本进入分发授权节点"

        if strictest.get("level") == LEVEL_WARN:
            # 警告不阻断：标注警告者，但仍放行到授权节点
            attempt["status"] = ATTEMPT_PASSED
            attempt["note"] = "存在警告级命中，警告不阻断，按通过放行并留痕"
            sample["current_node"] = NODE_AUTHORIZE
            sample["updated_at"] = _now()
            return sample, (
                f"尝试 {attempt['attempt_id']} 有警告表达式但无阻断，按严格者口径放行至授权节点"
            )

        # 最严格者为阻断：驳回，退回隔离节点继续修正
        attempt["status"] = ATTEMPT_REJECTED
        attempt["note"] = f"阻断表达式「{strictest.get('expression')}」命中，退回隔离节点"
        sample["current_node"] = NODE_QUARANTINE
        sample["updated_at"] = _now()
        return sample, (
            f"尝试 {attempt['attempt_id']} 被阻断表达式「{strictest.get('expression')}」驳回，"
            "样本退回隔离节点，需修正后重新重验"
        )

    def apply_authorization(
        self, sample_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """处置者申请分发资格。同一样本最多一份授权，争抢同一出口时后者被拒。"""
        sample = self.get_sample(sample_id)
        if sample is None:
            return None, f"隔离样本 {sample_id} 不存在或已归档"
        node = sample.get("current_node")
        if node in TERMINAL_NODES:
            return None, f"样本已到「{node}」终点，无需再申请授权"
        if node != NODE_AUTHORIZE:
            return None, f"样本当前在「{node}」，只有重验通过、到达授权节点后才能申请分发资格"
        if sample.get("authorization"):
            existing = sample["authorization"]
            return None, (
                f"该出口已由处置者「{existing.get('granted_to')}」取得授权（授权号 {existing.get('auth_code')}），"
                "数据分发模块最多获得一份授权，重复申请被拒绝"
            )

        operator = str(values.get("operator") or "值班管理员").strip()
        attempt = self._latest_attempt(sample)
        auth_code = f"AUTH-{sample['sample_code']}-{len(sample.get('attempts', [])):02d}"
        sample["authorization"] = {
            "auth_code": auth_code,
            "granted_to": operator,
            "granted_at": _now(),
            "based_on_attempt": attempt.get("attempt_id") if attempt else None,
            "rule_version": sample.get("active_rule_version"),
            "revoked": False,
        }
        sample["updated_at"] = _now()
        return sample, f"分发授权 {auth_code} 已签发给处置者「{operator}」，同一样本不再签发第二份"

    def confirm_delivery(
        self, sample_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """数据分发模块确认交付，生成不可变回执；没有授权不得交付。"""
        sample = self.get_sample(sample_id)
        if sample is None:
            return None, f"隔离样本 {sample_id} 不存在或已归档"
        if sample.get("current_node") == NODE_DELIVERED:
            return None, "样本已交付，回执不可重复生成"
        if sample.get("current_node") == NODE_ABANDONED:
            return None, "样本已放弃，不能再交付"
        if sample.get("current_node") != NODE_AUTHORIZE:
            return None, f"样本当前在「{sample.get('current_node')}」，未到授权节点，不能交付"
        auth = sample.get("authorization")
        if not auth or auth.get("revoked"):
            return None, "缺少有效分发授权，数据分发模块不能交付"

        target_system = str(values.get("target_system") or "数据仓库主通道").strip()
        receipt = {
            "receipt_code": f"RCPT-{sample['sample_code']}",
            "delivered_at": _now(),
            "target_system": target_system,
            "operator": str(values.get("operator") or auth.get("granted_to")).strip(),
            "auth_code": auth.get("auth_code"),
            # 证据冻结：交付时的规则版本、原值、候选值与尝试全部随回执固定
            "rule_version_frozen": sample.get("active_rule_version"),
            "original_value_frozen": sample.get("original_value"),
            "candidate_value_frozen": sample.get("candidate_value"),
            "attempt_id_frozen": auth.get("based_on_attempt"),
        }
        sample["receipt"] = receipt
        sample["current_node"] = NODE_DELIVERED
        sample["delivered_at"] = receipt["delivered_at"]
        sample["updated_at"] = _now()
        return sample, f"交付回执 {receipt['receipt_code']} 已生成，样本到达终点，证据冻结"

    def switch_rule_trial(
        self, sample_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """切换到新版规则做试验。

        已交付数据保持原证据、不切换；试验成功（重验通过）后需要重新申请分发资格，
        因此切换时若已有授权，授权作废并回到重验节点重新走一遍。
        """
        sample = self.get_sample(sample_id)
        if sample is None:
            return None, f"隔离样本 {sample_id} 不存在或已归档"
        node = sample.get("current_node")
        if node == NODE_DELIVERED:
            return None, "样本已交付，证据保持原规则版本，不允许再切换规则试验"
        if node == NODE_ABANDONED:
            return None, "样本已放弃，不再参与规则试验"
        new_version = str(values.get("rule_version") or "").strip()
        if not new_version:
            return None, "缺少新版规则版本号"
        if new_version == sample.get("active_rule_version"):
            return None, f"样本当前已经使用规则版本 {new_version}，无需切换"

        old_version = sample.get("active_rule_version")
        sample.setdefault("rule_version_history", []).append(
            {"version": old_version, "left_at": _now(), "reason": "切换新版规则试验"}
        )
        sample["active_rule_version"] = new_version
        # 试验资格不延续：旧授权作废，需重新走重验并重新申请
        if sample.get("authorization"):
            sample["authorization"]["revoked"] = True
            sample["authorization"]["revoke_reason"] = f"切换规则版本 {new_version} 试验，原授权失效"
            sample["authorization"] = None
        # 回到重验节点用新版规则重新评估；没有待决尝试时补一条试验尝试
        sample["current_node"] = NODE_REVALIDATE
        for attempt in sample.get("attempts", []):
            if attempt.get("status") == ATTEMPT_PENDING:
                attempt["status"] = ATTEMPT_STALE
                attempt["note"] = "规则版本切换，旧尝试作废"
        attempt_no = len(sample.get("attempts", [])) + 1
        sample.setdefault("attempts", []).append({
            "attempt_id": f"{sample['sample_code']}-A{attempt_no:02d}",
            "attempt_no": attempt_no,
            "rule_version": new_version,
            "candidate_value": sample.get("candidate_value"),
            "operator": str(values.get("operator") or "值班管理员").strip(),
            "status": ATTEMPT_PENDING,
            "created_at": _now(),
            "decided_at": None,
            "hits": [],
            "note": f"按新版规则 {new_version} 试验重验",
        })
        sample["updated_at"] = _now()
        return sample, (
            f"已切换到规则版本 {new_version} 试验；试验通过后需重新申请分发资格，"
            "已交付数据仍保留原版本证据"
        )

    def abandon_sample(
        self, sample_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """放弃样本：放弃即终点，之后任何迟到的通过结果都不能重新放行。"""
        sample = self.get_sample(sample_id)
        if sample is None:
            return None, f"隔离样本 {sample_id} 不存在或已归档"
        node = sample.get("current_node")
        if node in TERMINAL_NODES:
            return None, f"样本已处于「{node}」终态，不能重复放弃"
        reason = str(values.get("reason") or "").strip() or "处置者判定不再放行"
        for attempt in sample.get("attempts", []):
            if attempt.get("status") == ATTEMPT_PENDING:
                attempt["status"] = ATTEMPT_STALE
                attempt["note"] = "样本已放弃，待决尝试随之终止"
        sample["current_node"] = NODE_ABANDONED
        sample["abandoned_at"] = _now()
        sample["abandon_reason"] = reason
        sample["authorization"] = None
        sample["updated_at"] = _now()
        return sample, "样本已放弃并到达终点；此后迟到的重验通过结果不能重新放行"

    # ---------- 内部工具 ----------
    def _latest_attempt(self, sample: dict[str, Any]) -> dict[str, Any] | None:
        attempts = sample.get("attempts", [])
        return attempts[-1] if attempts else None

    def _normalize_hits(
        self, raw_hits: Any, fallback_result: Any
    ) -> list[dict[str, str]]:
        """把入参命中记录规整成统一结构；没有 hits 时按 result 兜底一条。"""
        hits: list[dict[str, str]] = []
        if isinstance(raw_hits, list):
            for item in raw_hits:
                if not isinstance(item, dict):
                    continue
                level = str(item.get("level") or LEVEL_PASS).strip()
                if level not in LEVEL_RANK:
                    level = LEVEL_PASS
                hits.append({
                    "expression": str(item.get("expression") or "未命名表达式"),
                    "level": level,
                    "message": str(item.get("message") or ""),
                })
        if not hits:
            result = str(fallback_result or LEVEL_PASS).strip()
            level = result if result in LEVEL_RANK else LEVEL_PASS
            hits.append({
                "expression": "默认校验表达式",
                "level": level,
                "message": "按提交结果生成的命中记录",
            })
        return hits

    def _strictest_hit(self, hits: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not hits:
            return None
        return max(hits, key=lambda hit: LEVEL_RANK.get(str(hit.get("level")), 0))
