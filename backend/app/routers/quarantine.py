"""隔离处置流转接口。

围绕样本在“隔离 → 重验 → 分发授权 → 已交付/已放弃”之间的流转提供动作入口，
所有节点核对、尝试版本与授权互斥逻辑由 QuarantineService 保证。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.quarantine import (
    ACTIVE_NODES,
    NODE_ORDER,
    TERMINAL_NODES,
    QuarantineService,
)

router = APIRouter(prefix="/api/validator/quarantine", tags=["结果校验-隔离处置"])

service = QuarantineService()


@router.get("/nodes", response_model=dict)
def node_meta() -> dict:
    """返回流转图节点顺序与节点性质，前端据此画图。"""
    return {
        "node_order": NODE_ORDER,
        "active_nodes": ACTIVE_NODES,
        "terminal_nodes": TERMINAL_NODES,
    }


@router.get("/stats", response_model=dict)
def stats() -> dict:
    """各节点在留样本数量，用于流转图角标。"""
    return service.stats()


@router.get("/samples", response_model=PageResult[dict])
def list_samples(
    node: str | None = Query(default=None, description="按当前节点过滤"),
    keyword: str | None = Query(default=None, description="按样本编号或数据集检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """隔离样本列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if node and node not in NODE_ORDER:
        raise HTTPException(status_code=400, detail=f"节点「{node}」不在流转图上")
    items, total = service.list_samples(node=node, keyword=keyword, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/samples/{sample_id}", response_model=dict)
def get_sample(sample_id: int) -> dict:
    """读取单个样本的完整流转明细（含尝试、命中、授权与回执）。"""
    sample = service.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"隔离样本 {sample_id} 不存在或已归档")
    result = dict(sample)
    result["stuck_reason"] = service.stuck_reason(sample)
    return result


@router.post("/samples/{sample_id}/correct", response_model=ActionResult)
def correct(sample_id: int, payload: EntryPayload) -> ActionResult:
    """修正候选值并送往重验节点，生成一条独立重验尝试。"""
    sample, message = service.correct(sample_id, payload.values)
    if sample is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=sample)


@router.post("/samples/{sample_id}/revalidate", response_model=ActionResult)
def revalidate(sample_id: int, payload: EntryPayload) -> ActionResult:
    """提交重验结论；旧尝试迟到的放行请求会在此被节点核对拦下。"""
    sample, message = service.submit_revalidation(sample_id, payload.values)
    if sample is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=sample)


@router.post("/samples/{sample_id}/authorize", response_model=ActionResult)
def authorize(sample_id: int, payload: EntryPayload) -> ActionResult:
    """申请分发资格；同一样本最多一份授权，争抢同一出口时后者被拒。"""
    sample, message = service.apply_authorization(sample_id, payload.values)
    if sample is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=sample)


@router.post("/samples/{sample_id}/deliver", response_model=ActionResult)
def deliver(sample_id: int, payload: EntryPayload) -> ActionResult:
    """确认交付并生成不可变回执，样本进入已交付终点。"""
    sample, message = service.confirm_delivery(sample_id, payload.values)
    if sample is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=sample)


@router.post("/samples/{sample_id}/trial", response_model=ActionResult)
def trial(sample_id: int, payload: EntryPayload) -> ActionResult:
    """切换新版规则试验；已交付数据保持原证据，试验成功需重新申请分发资格。"""
    sample, message = service.switch_rule_trial(sample_id, payload.values)
    if sample is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=sample)


@router.post("/samples/{sample_id}/abandon", response_model=ActionResult)
def abandon(sample_id: int, payload: EntryPayload) -> ActionResult:
    """放弃样本；放弃即终点，迟到的通过结果不能重新放行。"""
    sample, message = service.abandon_sample(sample_id, payload.values)
    if sample is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=sample)
