#!/usr/bin/env bash
# 隔离处置流转 API 端到端冒烟脚本：用 curl 真实走一遍 HTTP 接口。
set -u
BASE="http://127.0.0.1:8000/api/validator/quarantine"
PASS=0; FAIL=0

post() { # post <sample_id> <action> <json-values>
  curl -s -X POST "$BASE/samples/$1/$2" -H 'Content-Type: application/json' -d "{\"values\":$3}"
}
ok_field() { python3 -c "import sys,json;print(str(json.load(sys.stdin)['ok']).lower())"; }

assert_ok() { # assert_ok <name> <expected(true/false)> <json>
  local name="$1" expected="$2" json="$3"
  local actual; actual=$(printf '%s' "$json" | ok_field)
  if [ "$actual" = "$expected" ]; then echo "  ✓ $name"; PASS=$((PASS+1));
  else echo "  ✗ $name -> $json"; FAIL=$((FAIL+1)); fi
}

echo "== 节点元数据与统计 =="
curl -s "$BASE/nodes" | python3 -m json.tool
curl -s "$BASE/stats" | python3 -m json.tool
curl -s "$BASE/samples?size=100" | python3 -c "import sys,json;d=json.load(sys.stdin);print('样本总数:',d['total'])"

echo "== 1. 样本1：修正 -> 重验阻断（阻断+警告并存，按严格者驳回） =="
R=$(post 1 correct '{"candidate_value":"88.00","operator":"处置者乙"}')
assert_ok "修正生成新尝试" true "$R"
R=$(post 1 revalidate '{"hits":[{"expression":"w","level":"警告","message":"warn"},{"expression":"b","level":"阻断","message":"block"}]}')
assert_ok "阻断者决定出口，驳回" true "$R"
echo "$R" | python3 -c "import sys,json;d=json.load(sys.stdin);e=d['entry'];print('  当前节点:',e['current_node'],'| 最新尝试:',e['attempts'][-1]['status'])"

echo "== 2. 样本2：旧尝试迟到的放行请求被节点/尝试核对拦下 =="
R=$(post 2 correct '{"candidate_value":"13700137000","operator":"处置者甲"}')
assert_ok "新一轮修正使 A02 失效" true "$R"
R=$(post 2 revalidate '{"attempt_id":"SMP-2026-0002-A02","result":"通过"}')
assert_ok "旧尝试迟到放行被拒" false "$R"
R=$(post 2 revalidate '{"result":"通过"}')
assert_ok "当前尝试通过，进入授权节点" true "$R"
R=$(post 2 revalidate '{"result":"通过"}')
assert_ok "离开重验节点后再被节点核对拦下" false "$R"

echo "== 3. 样本3：两名处置者争同一出口，最多一份授权 =="
R=$(post 3 authorize '{"operator":"处置者甲"}')
assert_ok "处置者甲取得授权" true "$R"
R=$(post 3 authorize '{"operator":"处置者乙"}')
assert_ok "处置者乙重复申请被拒" false "$R"
R=$(post 3 deliver '{"target_system":"库存中台","operator":"处置者甲"}')
assert_ok "凭授权交付并生成回执" true "$R"
echo "$R" | python3 -c "import sys,json;e=json.load(sys.stdin)['entry'];print('  回执:',e['receipt']['receipt_code'],'| 冻结版本:',e['receipt']['rule_version_frozen'],'| 节点:',e['current_node'])"
R=$(post 3 deliver '{}')
assert_ok "重复交付被拒" false "$R"

echo "== 4. 样本4：已交付数据切换新版规则被拒，证据保持 =="
R=$(post 4 trial '{"rule_version":"v9"}')
assert_ok "已交付样本拒绝规则试验" false "$R"
curl -s "$BASE/samples/4" | python3 -c "import sys,json;e=json.load(sys.stdin);print('  活动版本:',e['active_rule_version'],'| 回执冻结版本:',e['receipt']['rule_version_frozen'])"

echo "== 5. 样本6：规则试验成功后需重新申请分发资格 =="
R=$(post 6 trial '{"rule_version":"v4","operator":"处置者甲"}')
assert_ok "切换新版规则试验，授权作废" true "$R"
echo "$R" | python3 -c "import sys,json;e=json.load(sys.stdin)['entry'];print('  节点:',e['current_node'],'| 版本:',e['active_rule_version'],'| 授权:',e['authorization'])"
R=$(post 6 revalidate '{"result":"通过"}')
assert_ok "试验重验通过" true "$R"
echo "$R" | python3 -c "import sys,json;e=json.load(sys.stdin)['entry'];print('  节点:',e['current_node'],'| 仍需重新申请授权:',e['authorization'] is None)"

echo "== 6. 样本2：放弃是终点，迟到通过不能重新放行 =="
R=$(post 2 abandon '{"reason":"源数据不可信"}')
assert_ok "放弃样本到达终点" true "$R"
R=$(post 2 revalidate '{"result":"通过"}')
assert_ok "迟到的通过结果被拒" false "$R"
R=$(post 2 correct '{"candidate_value":"x"}')
assert_ok "放弃后修正被拒" false "$R"
curl -s "$BASE/samples/2" | python3 -c "import sys,json;e=json.load(sys.stdin);print('  停留原因:',e['stuck_reason'])"

echo
echo "通过 $PASS 项，失败 $FAIL 项"
[ "$FAIL" -eq 0 ]
