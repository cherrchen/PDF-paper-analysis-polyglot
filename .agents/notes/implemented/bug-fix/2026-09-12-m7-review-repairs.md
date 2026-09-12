# Agent Note: M7 Review 修复

Status: implemented

[中文](./2026-09-12-m7-review-repairs.md) | [English](./2026-09-12-m7-review-repairs.en.md)

## 问题

2026-09-12 Code Review 建议 Request Changes：M7 仲裁与门禁的单元测试通过，但最小复现显示 Exit Gate 仍不成立。`fuse_page` 逐候选调用投票，归一化后占比恒为 1，authority 权重被抵消；TABLE/FORMULA 使用固定权重；`authorities()` 去空槽后再按位次赋权，把 fallback / 未注册 provider 当成 challenger。benchmark 把缺失 fixture 或指标变 null 当成 unchanged；校准诊断被标成 `REGRESSED`；错误门禁只读 `SECTION_STRUCTURE`。1→N 拆分会拆掉跨页续接；分段用宽松正则，数学行仍误拆段。本 Note 补充 [M7 落地 note](../architecture/2026-09-12-m7-parser-ensemble.md)，不引入真实 parser adapter 或区域级标注真值。

## 决策

1. **跨 provider 仲裁**：`fuse_page` 先把描述同一区域的候选聚类（含 TABLE/FORMULA），再调用一次 `fuse_candidate_labels`。页面级测试：交换 `layout.region` / `formula.detection` primary 后胜者改变；0.1 与 0.9 冲突时胜者占比不是 1.0。
2. **角色权重**：`authority_rank` 按 primary / challenger / fallback 槽位，未列出恒为 3。默认配置中 `TABLE/mock` = 1.0（fallback），`FORMULA/unknown` = 0.8。
3. **门禁**：基线 fixture 在当前报告中缺失 → `REGRESSED`；原可测指标变为 null → `REGRESSED`。校准准确率只输出 `diagnostic` 行。`issues` 同时给 `byCategory` 与 `bySeverity`；阻断计数是 ERROR+FATAL。WARNING/INFO 只观测。
4. **指标命名**：kinds / minCounts 检查改名为 `semanticExpectationCoverage`。`paragraphRecoveryAccuracy` 与 `sectionHierarchyAccuracy` 在无区域级真值时恒为 null。
5. **续接与数学守卫**：continuation group 拆分后仍在边界合并非标题片段，SourceAnchor 保留多个 region。分段判定复用 `heading_decision`，`2 dx = dy` 不再把一段拆成三截。
6. **其它收口**：`load_registry()` 返回只读映射；`columns_separated` 把列聚类提到循环外；`pipeline.en.md` 补上 M7 路由说明。

## 考虑过的替代方案

- 保持逐候选融合、只改单测：复现显示交换 primary 结果不变，Exit Gate 仍假绿。
- 把校准相对下降继续当门禁：与决策「校准只作诊断」冲突，且未标注区域的正确新增也会触发下降。
- 继续用 `SECTION_STRUCTURE` 代理错误数：其它类别的 ERROR 会漏报。

## 后果

- Phase 7.4 的 authority 权重现在能改变 `fuse_page` 的胜者；7.7 门禁会在 fixture/指标消失时失败。
- 验证：`just test-python` 408 passed，覆盖率 90.10%；Python lint、Pyright、双语检查通过。完整 CI 与 `just benchmark` 未作为本修复的阻断项运行。
- 当前态：[M7 落地 note](../architecture/2026-09-12-m7-parser-ensemble.md)、[`docs/architecture/pipeline.md`](../../../../docs/architecture/pipeline.md)、[`docs/development/roadmap.md`](../../../../docs/development/roadmap.md) M7 明细。
