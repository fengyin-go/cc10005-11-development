"""隔离处置流转状态机的不变量测试（不依赖 pytest，直接 python 运行）。

覆盖需求里的关键口径：
- 每次重验生成独立尝试，旧尝试迟到的放行请求被节点核对拦下；
- 阻断与警告并存时按最严格者决定出口；
- 同一出口最多一份授权，两名处置者争抢后者被拒；
- 新版规则试验不改写已交付证据，试验通过需重新申请资格；
- 放弃即终点，迟到的通过结果不能重新放行。
"""
from __future__ import annotations

import sys

from app.services.quarantine import (
    ATTEMPT_PASSED,
    ATTEMPT_PENDING,
    ATTEMPT_REJECTED,
    ATTEMPT_STALE,
    LEVEL_BLOCK,
    LEVEL_WARN,
    NODE_ABANDONED,
    NODE_AUTHORIZE,
    NODE_DELIVERED,
    NODE_QUARANTINE,
    NODE_REVALIDATE,
    QuarantineService,
)
from app.store import store

MODULE = "quarantine_sample"


def reset() -> None:
    """每个用例前重建内存表，避免用例间互相污染。"""
    from app.quarantine_seed import QUARANTINE_SEED_ROWS

    store._tables[MODULE] = [dict(row) for row in QUARANTINE_SEED_ROWS]
    # 深拷贝嵌套结构
    for row in store._tables[MODULE]:
        row["hits"] = [dict(hit) for hit in row.get("hits", [])]
        row["attempts"] = [dict(a, hits=[dict(h) for h in a.get("hits", [])]) for a in row.get("attempts", [])]
        if row.get("authorization"):
            row["authorization"] = dict(row["authorization"])
        if row.get("receipt"):
            row["receipt"] = dict(row["receipt"])


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"用例失败：{name} {detail}")
    print(f"  ✓ {name}")


def test_correct_creates_independent_attempt() -> None:
    print("用例1：修正生成独立尝试，旧待决尝试被标记取代")
    reset()
    svc = QuarantineService()
    sample, msg = svc.correct(2, {"candidate_value": "13900139000", "operator": "处置者甲"})
    check("样本进入重验节点", sample["current_node"] == NODE_REVALIDATE)
    check("尝试数量增加", len(sample["attempts"]) == 3)
    check("旧待决尝试被取代", sample["attempts"][1]["status"] == ATTEMPT_STALE)
    check("新尝试待重验", sample["attempts"][2]["status"] == ATTEMPT_PENDING)
    check("新尝试带当前规则版本", sample["attempts"][2]["rule_version"] == "v3")
    # 空候选值必须被拒
    sample2, msg2 = svc.correct(1, {"candidate_value": "  "})
    check("空候选值被拒", sample2 is None and "候选值不能为空" in msg2)


def test_late_pass_from_stale_attempt_blocked() -> None:
    print("用例2：旧尝试迟到的放行请求核对当前节点后被拒，不能越过校验")
    reset()
    svc = QuarantineService()
    # 样本2 已在重验节点且 A02 待决；先制造一轮新修正，让 A02 变成旧尝试
    svc.correct(2, {"candidate_value": "13700137000", "operator": "处置者甲"})
    sample = store.find(MODULE, 2)
    stale_id = "SMP-2026-0002-A02"
    # 旧尝试迟到的“通过”放行请求
    late, msg = svc.submit_revalidation(
        2, {"attempt_id": stale_id, "result": "通过"}
    )
    check("迟到放行被拒", late is None and "不是当前有效尝试" in msg, msg)
    check("样本仍停在重验节点", store.find(MODULE, 2)["current_node"] == NODE_REVALIDATE)
    # 当前有效尝试正常通过后才能前进
    ok, _ = svc.submit_revalidation(2, {"result": "通过"})
    check("当前尝试通过后进入授权节点", ok["current_node"] == NODE_AUTHORIZE)
    # 已不在重验节点时，任何重验请求都被节点核对拦下
    late2, msg2 = svc.submit_revalidation(2, {"result": "通过"})
    check("非重验节点的请求被节点核对拦下", late2 is None and "核对当前节点失败" in msg2, msg2)


def test_strictest_level_decides_exit() -> None:
    print("用例3：阻断与警告并存，按最严格者决定出口")
    reset()
    svc = QuarantineService()
    # 样本1 隔离中：先修正送入重验
    svc.correct(1, {"candidate_value": "88.00", "operator": "处置者乙"})
    # 重验同时命中阻断+警告
    rejected, msg = svc.submit_revalidation(1, {
        "hits": [
            {"expression": "warn_expr", "level": LEVEL_WARN, "message": "仅警告"},
            {"expression": "block_expr", "level": LEVEL_BLOCK, "message": "硬阻断"},
        ]
    })
    check("阻断者决定出口：驳回", rejected["current_node"] == NODE_QUARANTINE, msg)
    latest = rejected["attempts"][-1]
    check("尝试状态为重验驳回", latest["status"] == ATTEMPT_REJECTED)
    check("驳回说明指向阻断表达式", "block_expr" in latest["note"])
    # 再次重验只有警告：警告不阻断，放行
    svc.correct(1, {"candidate_value": "88.00", "operator": "处置者乙"})
    warned, msg = svc.submit_revalidation(1, {
        "hits": [{"expression": "warn_expr", "level": LEVEL_WARN, "message": "仅警告"}]
    })
    check("警告不阻断：放行至授权节点", warned["current_node"] == NODE_AUTHORIZE, msg)
    check("尝试仍记为重验通过并留痕", warned["attempts"][-1]["status"] == ATTEMPT_PASSED)


def test_authorization_mutex() -> None:
    print("用例4：两名处置者争同一出口，最多一份授权")
    reset()
    svc = QuarantineService()
    first, msg1 = svc.apply_authorization(3, {"operator": "处置者甲"})
    check("第一份授权签发", first["authorization"] is not None and first["authorization"]["granted_to"] == "处置者甲")
    second, msg2 = svc.apply_authorization(3, {"operator": "处置者乙"})
    check("第二份授权被拒", second is None and "最多获得一份授权" in msg2, msg2)
    check("授权仍属于处置者甲", store.find(MODULE, 3)["authorization"]["granted_to"] == "处置者甲")
    # 未到授权节点不能申请
    bad, msg3 = svc.apply_authorization(1, {"operator": "处置者甲"})
    check("隔离节点不能申请授权", bad is None and "只有重验通过" in msg3, msg3)


def test_delivery_freezes_evidence() -> None:
    print("用例5：交付生成回执并冻结证据，重复交付被拒")
    reset()
    svc = QuarantineService()
    # 样本6 已有授权，直接交付
    delivered, msg = svc.confirm_delivery(6, {"target_system": "物流数仓", "operator": "处置者甲"})
    check("样本到达已交付终点", delivered["current_node"] == NODE_DELIVERED)
    receipt = delivered["receipt"]
    check("回执冻结规则版本", receipt["rule_version_frozen"] == "v3")
    check("回执冻结原值与候选值", receipt["original_value_frozen"] == "720" and receipt["candidate_value_frozen"] == "48")
    again, msg2 = svc.confirm_delivery(6, {})
    check("重复交付被拒", again is None and "不可重复生成" in msg2, msg2)
    # 无授权不能交付（样本3 在授权节点但未授权）
    no_auth, msg3 = svc.confirm_delivery(3, {})
    check("无授权不能交付", no_auth is None and "缺少有效分发授权" in msg3, msg3)


def test_rule_trial_keeps_delivered_evidence() -> None:
    print("用例6：新版规则试验不改写已交付证据，试验通过需重新申请资格")
    reset()
    svc = QuarantineService()
    # 已交付样本不允许切换
    blocked, msg = svc.switch_rule_trial(4, {"rule_version": "v9"})
    check("已交付样本拒绝切换规则", blocked is None and "证据保持原规则版本" in msg, msg)
    frozen = store.find(MODULE, 4)
    check("交付证据仍为原版本", frozen["receipt"]["rule_version_frozen"] == "v2" and frozen["active_rule_version"] == "v2")
    # 样本3 在授权节点：切换后授权作废、回重验节点
    trial, msg2 = svc.switch_rule_trial(3, {"rule_version": "v4", "operator": "处置者乙"})
    check("切换后回到重验节点", trial["current_node"] == NODE_REVALIDATE, msg2)
    check("活动规则版本变为 v4", trial["active_rule_version"] == "v4")
    check("历史保留旧版本", trial["rule_version_history"][-1]["version"] == "v3")
    check("新试验尝试待重验", trial["attempts"][-1]["status"] == ATTEMPT_PENDING)
    # 试验通过后到达授权节点，且没有授权，必须重新申请
    passed, _ = svc.submit_revalidation(3, {"result": "通过"})
    check("试验通过后停在授权节点", passed["current_node"] == NODE_AUTHORIZE)
    check("需要重新申请分发资格", passed["authorization"] is None)


def test_abandon_is_terminal() -> None:
    print("用例7：放弃是终点，迟到的通过结果不能重新放行")
    reset()
    svc = QuarantineService()
    abandoned, msg = svc.abandon_sample(2, {"reason": "源数据不可信"})
    check("样本到达已放弃终点", abandoned["current_node"] == NODE_ABANDONED, msg)
    check("待决尝试随放弃终止", all(a["status"] != ATTEMPT_PENDING for a in abandoned["attempts"]))
    # 迟到的重验通过
    late, msg2 = svc.submit_revalidation(2, {"result": "通过"})
    check("迟到通过被拒", late is None and "终点" in msg2, msg2)
    check("样本仍在已放弃", store.find(MODULE, 2)["current_node"] == NODE_ABANDONED)
    # 放弃后不能再修正、授权、交付
    check("放弃后修正被拒", svc.correct(2, {"candidate_value": "x"})[0] is None)
    check("放弃后授权被拒", svc.apply_authorization(2, {"operator": "甲"})[0] is None)
    check("放弃后交付被拒", svc.confirm_delivery(2, {})[0] is None)
    check("重复放弃被拒", svc.abandon_sample(2, {})[0] is None)


def test_full_happy_path() -> None:
    print("用例8：隔离 → 修正 → 重验 → 授权 → 交付 全链路")
    reset()
    svc = QuarantineService()
    svc.correct(1, {"candidate_value": "88.00", "operator": "处置者乙"})
    sample, _ = svc.submit_revalidation(1, {"result": "通过"})
    check("重验通过", sample["current_node"] == NODE_AUTHORIZE)
    sample, _ = svc.apply_authorization(1, {"operator": "处置者乙"})
    check("授权签发", sample["authorization"]["granted_to"] == "处置者乙")
    sample, _ = svc.confirm_delivery(1, {"target_system": "价格中台"})
    check("交付完成", sample["current_node"] == NODE_DELIVERED and bool(sample["receipt"]))


def main() -> int:
    tests = [
        test_correct_creates_independent_attempt,
        test_late_pass_from_stale_attempt_blocked,
        test_strictest_level_decides_exit,
        test_authorization_mutex,
        test_delivery_freezes_evidence,
        test_rule_trial_keeps_delivered_evidence,
        test_abandon_is_terminal,
        test_full_happy_path,
    ]
    for test in tests:
        test()
    print(f"\n全部 {len(tests)} 组不变量用例通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
