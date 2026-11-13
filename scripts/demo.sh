#!/bin/bash
# 端到端演示：导入 -> 去重 -> 冲突复核 -> 批次结论 -> 报告批准/待处理视图。
# 前置：服务已在 http://127.0.0.1:8000 运行，参考数据已 seed。
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
IH="Authorization: Bearer token-inspector-001"
RH="Authorization: Bearer token-reviewer-001"
py() { python3 -c "import sys,json;x=json.load(sys.stdin);$1"; }

echo "== 1. 健康检查 =="
curl -s "$BASE/health"; echo

echo "== 2. 导入 LAB-A CSV（坏行进入待处理，不丢行） =="
curl -s -X POST "$BASE/api/import/records" -H "$IH" \
  -F "source_ref=LAB-A" -F "file=@data/raw/lab_a_20261105.csv" \
  | py "print('status=',x['status'],'total=',x['total_rows'],'parsed=',x['parsed_rows'],'pending=',x['pending_rows'])"

echo "== 3. 同文件重传（来源编号+指纹识别为重复，跳过） =="
curl -s -X POST "$BASE/api/import/records" -H "$IH" \
  -F "source_ref=LAB-A" -F "file=@data/raw/lab_a_20261105.csv" \
  | py "print('status=',x['status'],'note=',x['note'])"

echo "== 4. 导入 LAB-B JSON（异源结果不一致 -> 列冲突，不覆盖） =="
curl -s -X POST "$BASE/api/import/records" -H "$IH" \
  -F "source_ref=LAB-B" -F "file=@data/raw/lab_b_20261105.json" \
  | py "print('conflicts_raised=',x['conflicts_raised'])"

echo "== 5. 复核员查看并处理冲突（采信 LAB-B 的 0.35 mg/kg 高值） =="
CID=$(curl -s "$BASE/api/review/conflicts?status=open" -H "$RH" \
  | py "print(x[0]['id'])")
KEEP=$(curl -s "$BASE/api/query/samples/S-001/groups" -H "$IH" | py "
g=[g for g in x if g['analyte']=='lead'][0]
print([r['id'] for r in g['results'] if r['record_no']=='RB-001'][0])")
echo "conflict_id=$CID, keep result_id=$KEEP"
curl -s -X POST "$BASE/api/review/conflicts/$CID/resolve" -H "$RH" -H "Content-Type: application/json" \
  -d "{\"keep_result_id\":$KEEP,\"note\":\"演示：复测采信LAB-B高值\"}" \
  | py "print('conflict status=',x['status'])"

echo "== 6. 生成批次结论（固体 B20261101=hold，液体 B20261102=pass） =="
curl -s -X POST "$BASE/api/reports/batch-conclusions" -H "$IH" -H "Content-Type: application/json" \
  -d '{"batch_no":"B20261101"}' \
  | py "print('B20261101 =>',x['conclusion'],'| 阻断数=',len(x['detail']['blockers']))"
LCID=$(curl -s -X POST "$BASE/api/reports/batch-conclusions" -H "$IH" -H "Content-Type: application/json" \
  -d '{"batch_no":"B20261102"}' | py "print(x['id'])")

echo "== 7. 提交并批准液体批次报告 =="
RID=$(curl -s -X POST "$BASE/api/reports/submit" -H "$IH" -H "Content-Type: application/json" \
  -d "{\"batch_no\":\"B20261102\",\"batch_conclusion_id\":$LCID}" | py "print(x['id'])")
curl -s -X POST "$BASE/api/reports/$RID/approve" -H "$RH" \
  | py "print('report',x['id'],'=>',x['status'])"

echo "== 8. 待处理视图（采购可见的不确定项） =="
curl -s "$BASE/api/query/pending?batch_no=B20261101" -H "$IH" \
  | py "print('raw_pending(坏行)=',len(x['raw_pending']),'result_pending(待补/总量挂起)=',len(x['result_pending']))"

echo "== 9. 批次报告视图中的关键判定 =="
curl -s "$BASE/api/query/batches/B20261101/report" -H "$IH" | py "
c=x['latest_conclusion']
print('结论=',c['conclusion'])
for it in c['detail']['items']:
    if it['analyte'] in ('lead','mercury') and it['sample_no'] in ('S-001','S-002'):
        print(' ',it['sample_no'],it['analyte'],it['verdict'],it['interval'],it['limit'])"

echo
echo "演示完成。Swagger UI: $BASE/docs"
