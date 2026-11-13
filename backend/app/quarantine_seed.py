"""隔离处置流转的示例样本。

每个样本带原值与进入隔离时的规则版本，刻意覆盖：
- 阻断与警告表达式同时命中、按最严格者决定出口；
- 多轮独立重验尝试、旧尝试被取代；
- 授权争抢、已交付证据冻结、已放弃终点。
"""
from __future__ import annotations

from typing import Any

QUARANTINE_SEED_ROWS: list[dict[str, Any]] = [
    {
        "id": 1,
        "sample_code": "SMP-2026-0001",
        "dataset": "商品价格快照",
        "field_name": "price",
        "original_value": "-99.00",
        "candidate_value": None,
        "rule_code": "VALI-0001",
        "active_rule_version": "v3",
        "current_node": "隔离节点",
        "hits": [
            {
                "expression": "price >= 0",
                "level": "阻断",
                "message": "价格不允许为负数",
            },
            {
                "expression": "price <= 1000000",
                "level": "警告",
                "message": "价格量级偏高，请人工复核",
            },
        ],
        "attempts": [],
        "authorization": None,
        "receipt": None,
        "rule_version_history": [],
        "created_at": "2026-11-10 09:12:30",
        "updated_at": "2026-11-10 09:12:30",
        "pending": True,
        "abnormal": True,
    },
    {
        "id": 2,
        "sample_code": "SMP-2026-0002",
        "dataset": "商户联系信息",
        "field_name": "contact_phone",
        "original_value": "12345",
        "candidate_value": "13800138000",
        "rule_code": "VALI-0002",
        "active_rule_version": "v3",
        "current_node": "重验节点",
        "hits": [
            {
                "expression": "regex_match(phone, '^1[3-9]\\d{9}$')",
                "level": "阻断",
                "message": "手机号格式不符合 11 位规范",
            }
        ],
        "attempts": [
            {
                "attempt_id": "SMP-2026-0002-A01",
                "attempt_no": 1,
                "rule_version": "v2",
                "candidate_value": "010-8888",
                "operator": "处置者甲",
                "status": "重验驳回",
                "created_at": "2026-11-10 10:02:11",
                "decided_at": "2026-11-10 10:05:42",
                "hits": [
                    {
                        "expression": "regex_match(phone, '^1[3-9]\\d{9}$')",
                        "level": "阻断",
                        "message": "仍非手机号格式",
                    }
                ],
                "note": "阻断表达式命中，退回隔离节点",
            },
            {
                "attempt_id": "SMP-2026-0002-A02",
                "attempt_no": 2,
                "rule_version": "v3",
                "candidate_value": "13800138000",
                "operator": "处置者甲",
                "status": "待重验",
                "created_at": "2026-11-11 14:20:03",
                "decided_at": None,
                "hits": [],
                "note": "候选值已送入重验节点，等待结论",
            },
        ],
        "authorization": None,
        "receipt": None,
        "rule_version_history": [
            {"version": "v2", "left_at": "2026-11-11 14:18:00", "reason": "切换新版规则试验"}
        ],
        "created_at": "2026-11-10 09:40:12",
        "updated_at": "2026-11-11 14:20:03",
        "pending": True,
        "abnormal": True,
    },
    {
        "id": 3,
        "sample_code": "SMP-2026-0003",
        "dataset": "库存快照",
        "field_name": "stock_count",
        "original_value": "999999",
        "candidate_value": "1200",
        "rule_code": "VALI-0004",
        "active_rule_version": "v3",
        "current_node": "分发授权节点",
        "hits": [
            {
                "expression": "stock_count <= 100000",
                "level": "警告",
                "message": "库存超过常规上限，仅警告不阻断",
            }
        ],
        "attempts": [
            {
                "attempt_id": "SMP-2026-0003-A01",
                "attempt_no": 1,
                "rule_version": "v3",
                "candidate_value": "1200",
                "operator": "处置者乙",
                "status": "重验通过",
                "created_at": "2026-11-11 16:00:21",
                "decided_at": "2026-11-11 16:03:55",
                "hits": [
                    {
                        "expression": "stock_count <= 100000",
                        "level": "警告",
                        "message": "库存超过常规上限，仅警告不阻断",
                    }
                ],
                "note": "存在警告级命中，警告不阻断，按通过放行并留痕",
            }
        ],
        "authorization": None,
        "receipt": None,
        "rule_version_history": [],
        "created_at": "2026-11-11 15:51:40",
        "updated_at": "2026-11-11 16:03:55",
        "pending": True,
        "abnormal": False,
    },
    {
        "id": 4,
        "sample_code": "SMP-2026-0004",
        "dataset": "订单金额流水",
        "field_name": "order_amount",
        "original_value": "0",
        "candidate_value": "259.90",
        "rule_code": "VALI-0005",
        "active_rule_version": "v2",
        "current_node": "已交付",
        "hits": [
            {
                "expression": "order_amount > 0",
                "level": "阻断",
                "message": "订单金额必须大于 0",
            }
        ],
        "attempts": [
            {
                "attempt_id": "SMP-2026-0004-A01",
                "attempt_no": 1,
                "rule_version": "v2",
                "candidate_value": "259.90",
                "operator": "处置者乙",
                "status": "重验通过",
                "created_at": "2026-11-09 11:10:00",
                "decided_at": "2026-11-09 11:14:20",
                "hits": [],
                "note": "重验通过，样本可前往分发授权节点",
            }
        ],
        "authorization": {
            "auth_code": "AUTH-SMP-2026-0004-01",
            "granted_to": "处置者乙",
            "granted_at": "2026-11-09 11:20:00",
            "based_on_attempt": "SMP-2026-0004-A01",
            "rule_version": "v2",
            "revoked": False,
        },
        "receipt": {
            "receipt_code": "RCPT-SMP-2026-0004",
            "delivered_at": "2026-11-09 11:32:08",
            "target_system": "财务数仓 ODS",
            "operator": "处置者乙",
            "auth_code": "AUTH-SMP-2026-0004-01",
            "rule_version_frozen": "v2",
            "original_value_frozen": "0",
            "candidate_value_frozen": "259.90",
            "attempt_id_frozen": "SMP-2026-0004-A01",
        },
        "rule_version_history": [],
        "created_at": "2026-11-09 10:58:00",
        "updated_at": "2026-11-09 11:32:08",
        "delivered_at": "2026-11-09 11:32:08",
        "pending": False,
        "abnormal": False,
    },
    {
        "id": 5,
        "sample_code": "SMP-2026-0005",
        "dataset": "评价情感分",
        "field_name": "sentiment_score",
        "original_value": "12.8",
        "candidate_value": "0.92",
        "rule_code": "VALI-0006",
        "active_rule_version": "v3",
        "current_node": "已放弃",
        "hits": [
            {
                "expression": "sentiment_score between 0 and 1",
                "level": "阻断",
                "message": "情感分越界",
            },
            {
                "expression": "sentiment_score is not null",
                "level": "警告",
                "message": "历史上出现过空值，提醒关注",
            }
        ],
        "attempts": [
            {
                "attempt_id": "SMP-2026-0005-A01",
                "attempt_no": 1,
                "rule_version": "v3",
                "candidate_value": "0.92",
                "operator": "处置者甲",
                "status": "已被新尝试取代",
                "created_at": "2026-11-08 15:00:00",
                "decided_at": None,
                "hits": [],
                "note": "样本已放弃，待决尝试随之终止",
            }
        ],
        "authorization": None,
        "receipt": None,
        "rule_version_history": [],
        "created_at": "2026-11-08 14:40:00",
        "updated_at": "2026-11-08 17:05:00",
        "abandoned_at": "2026-11-08 17:05:00",
        "abandon_reason": "源页面已下线，无法取得可信候选值，处置者放弃",
        "pending": False,
        "abnormal": True,
    },
    {
        "id": 6,
        "sample_code": "SMP-2026-0006",
        "dataset": "物流时效",
        "field_name": "delivery_hours",
        "original_value": "720",
        "candidate_value": "48",
        "rule_code": "VALI-0007",
        "active_rule_version": "v3",
        "current_node": "分发授权节点",
        "hits": [
            {
                "expression": "delivery_hours <= 168",
                "level": "警告",
                "message": "时效偏长，警告留痕",
            }
        ],
        "attempts": [
            {
                "attempt_id": "SMP-2026-0006-A01",
                "attempt_no": 1,
                "rule_version": "v3",
                "candidate_value": "48",
                "operator": "处置者甲",
                "status": "重验通过",
                "created_at": "2026-11-12 09:00:00",
                "decided_at": "2026-11-12 09:04:10",
                "hits": [
                    {
                        "expression": "delivery_hours <= 168",
                        "level": "警告",
                        "message": "时效偏长，警告留痕",
                    }
                ],
                "note": "存在警告级命中，警告不阻断，按通过放行并留痕",
            }
        ],
        "authorization": {
            "auth_code": "AUTH-SMP-2026-0006-01",
            "granted_to": "处置者甲",
            "granted_at": "2026-11-12 09:10:00",
            "based_on_attempt": "SMP-2026-0006-A01",
            "rule_version": "v3",
            "revoked": False,
        },
        "receipt": None,
        "rule_version_history": [],
        "created_at": "2026-11-12 08:50:00",
        "updated_at": "2026-11-12 09:10:00",
        "pending": True,
        "abnormal": False,
    },
]
