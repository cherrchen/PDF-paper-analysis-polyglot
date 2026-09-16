# Agent Note: 真实论文端到端验收发现的三处缺陷

Status: implemented

[中文](./2026-09-16-real-paper-acceptance-defects.md) | [English](./2026-09-16-real-paper-acceptance-defects.en.md)

## 问题

用真实论文（NIPS 2017 *Attention Is All You Need*，11 页 camera-ready、569 KB）在运行中的本地栈上走一遍 PRD §40 产品流：`just serve-reader` 三进程（API + worker + Vite），浏览器导入面板提交绝对路径，真实 provider（`deepseek-flash` @ `https://api.deepseek.com`，逐节点调用）。三处缺陷暴露，且都不在合成夹具的覆盖范围内。

**1. 重复 Issue id 让整次运行在最后一阶段硬失败。**

语义恢复对同一节点内重复出现的未解析引用各记一条 Issue，而 `RecoveryBuilder.issue()` 的 id 是 `stable_uuid(layout.id, "issue", category, message)`——`(category, message)` 的内容地址。论文结果表那一行（`Model EN-FR ByteNet [15] … GNMT + RL [31] … GNMT + RL Ensemble [31] …`）里 `[31]` 出现两次、两次都未解析，于是生成两条**完全相同**的 Issue（同 id、同 message、同 `affectedIds`）。后果不是少一条警告：

```text
job e7e4da2b…  2026-09-16T10:50:17Z 提交 → 11:00:25Z failed（10 分 8 秒）
stage: index
error: index stage failed: bundle reference issues:
       ['semantic document issues: duplicate id 88a3b837-2e79-b14a-7202-0affcd8d4195']
```

`_run_index_stage` / `rerender_workspace` 在发布前跑 `validate_bundle_references`，其中 `_check_local_stores` 对每份 bundle 文档校验本地 store 的重复 id。命中即 INDEX 抛错，作业判 `failed`，**viewer 永不发布**。此时 physical/layout/semantic/translate/render 全部已完成：`translation.json`、`target.pdf`、`build/` 都在盘上，10 分钟的 LLM 调用白费，用户拿不到任何产物。合成夹具里同一节点的同一引用号只出现一次，所以既有 golden、benchmark 与 e2e 全绿也发现不了。

**2. 导入面板在 280 s 后放弃仍在运行的作业。**

`import-panel.ts` 的 `POLL_DEADLINE_MS = 280_000`。同一篇论文：面板 18:50:17 提交，18:54:57（第 280 s）显示 `Job still running · refresh to check` 并重新启用提交按钮，而作业实际在 19:00:25 才结束（失败，见上）。面板因此**不再跟随**，即使作业随后成功也不会调用 `DualPaneReader.load()` 就地换到新修订——阅读器停在旧修订（`f0293403791d4287b2e9c5d10cc7e991`，anatomy 夹具），用户只能手动刷新页面。批次 F e2e 用的 tikz-vector 只需约 2 s，所以 280 s 从未被真正考验过；真实 LLM 下 11 页论文要 183 次调用（134 个文本节点 + 49 个表格单元），约 10 分钟。

**3. 热缓存跨进程读不回来：TRANSLATE 直接抛校验错。**

修完前两处后重跑同一 workspace，TRANSLATE 阶段立刻失败：

```text
job 19d82d5a…  2026-09-16T11:07:28Z failed
stage: translate
error: translate stage failed: 1 validation error for InlineMark
       Value error, explicit null is not allowed for: href
```

`TranslationCache.put` 用 `mark.model_dump()` 写行，把未设置的可选属性一并写成 `"href": null`；而 `InlineMark` 把 `href` / `label` / `targetNodeId` 声明为**不可显式 null 的可选属性**，`get`/构造索引时 `model_validate` 拒绝该行。首次运行冷缓存（只写不读）所以看不出来；任何 warm 运行（重跑、换 render 配置、`rerender_workspace` 全量重译）都会在装载缓存那一刻失败。178 行缓存里 24 行带 mark，全部中招。既有 `test_cache.py` 只测「翻译失败不写缓存」，没有一行把带 mark 的行读回来。

## 决策

1. **Issue 按 id 去重（`pdf_pipeline.semantic`）。** `RecoveryBuilder` 增加 `self._issue_ids`，`issue()` 在 id 已存在时直接返回，与既有 `relation()` 用 `_relation_keys` 去重的写法一致。理由：id 就是内容地址，`IssueStore.issues` 的 id 唯一是文档契约（`validate_bundle_references` 校验、发布前提），同一问题出现两次仍是一个问题。不放宽校验器：重复 id 仍是真信号，只是语义恢复不该产出它。
2. **SEMANTIC producer 升 `0.1.0` → `0.2.0`（`SEMANTIC_PRODUCER_VERSION`）。** 阶段产物字节变了（少一条重复 Issue），既有 workspace 的 SEMANTIC 记录必须失配重跑；否则用户重试时会复用一个永远不会通过发布的 `semantic.json`，且 GUI 没有 `--rerun-from` 入口，等于永久卡死。这带来一处 golden 更新：`tests/golden/smoke/semantic.json` 的 8 条 provenance `producerVersion` 从 `0.1.0` 改为 `0.2.0`，属[golden 政策](../../../../docs/testing/golden.md)第 2 类（期望契约有意变更），其余字段未动。
3. **导入面板跟随作业到终态（`apps/web/src/import-panel.ts`）。** 删除 `POLL_DEADLINE_MS` 与 `Job still running · refresh to check`；轮询在 `queued`/`running` 上继续，在 `succeeded`/`failed` 上结束。运行中状态行改为 `Job <status> · <id 前 8 位> · <已用时>`（`elapsedLabel`），因为作业记录的 `stage` 只在失败时才写，客户端唯一能显示的活性信号就是自己的已用时。作业记录仍是权威：面板不猜测、不提前下结论。
4. **缓存行按规范形存 mark，读侧归一化历史 null（`paper_llm.cache`）。** `put` 改 `mark.model_dump(exclude_none=True)`；装载时用 `_stored_mark` 丢弃值为 null 的属性再 `model_validate`。不升 `TRANSLATION_CACHE_VERSION`：版本号管的是**键派生规则与行义**，而「null 属性 = 缺失」在 `InlineMark` 上语义唯一（该模型没有 required-nullable 字段），既不会误命中也没有歧义；升版本只会把 178 条已翻译好的行丢掉，让用户为一个序列化缺陷重付一次 provider 费用。

## 考虑过的替代方案

- **放宽 `validate_bundle_references` 对重复 id 的判定**：等于把「store 的 id 唯一」这条契约从发布检查里删掉，换来的是一个永远查不出重复 Issue 的盲点；重复 id 会让 ERROR 统计与 viewer 问题列表重复计数的真实风险仍然存在。修生产者，不删检查。
- **给每次出现发一条带位置的 Issue（把 mark 偏移折进 id）**：message 里没有偏移，两条「同一节点同一引用号」的 Issue 对用户不可区分，只会把问题列表变长；真要按位置区分需要新的 message/定位模型，超出本次范围。
- **保留截止但把 280 s 调大（如 30 分钟）**：只是把同一个错误推迟到更慢的论文上，并把「多长算够」变成又一个常量。作业记录本身有终态，客户端没有理由自己定死线。
- **worker 在 job 记录里写运行中的 stage（进度条）**：需要 pipeline 阶段回调 → 记录原子重写的通道，改动面覆盖批次 B 的状态机与并发语义；本次验收只要求流程不再中断，进度显示作为后续增强，不在本 note 内。
- **不升 producer 版本，让用户换 workspace 路径或删目录**：把修复的成本转嫁给用户，且失败现象完全相同（同样的 `duplicate id`），排障时看不出「重建即可」。阶段版本就是为这种「产物语义变了」准备的旋钮。
- **面板在截止后重新启用提交按钮并让用户重跑**：重跑同一个 workspace 只会复用同一批已完成阶段，重复失败，不解决问题。
- **缓存升 `TRANSLATION_CACHE_VERSION` 而不是读侧归一化**：符合「旧行一律忽略」的字面约定，但会丢掉 178 条语义完好的翻译行，让真实用户为一个序列化缺陷重付 provider 费用；而且它并没有让「null = 缺失」这条事实有归属，下一个写到 null 的写入方仍会踩同一个坑。
- **只修写入方、不管存量行**：已写坏的行会一直让后续运行在装载缓存时失败，等于把「重建缓存」写成用户手册里的一条隐性要求。
- **给 `_CanonicalModel` 加一个「容忍显式 null」的宽松模式**：会把契约里「存在」与「null」的区分在全局抹平，影响所有 canonical 文档的校验，远超这个缓存行的范围。

## 后果

- `packages/python/pdf-pipeline/src/pdf_pipeline/semantic.py`：`_issue_ids` + `issue()` 幂等（含说明 docstring）；`SEMANTIC_PRODUCER_VERSION = "0.2.0"`。
- `apps/web/src/import-panel.ts`：删除 `POLL_DEADLINE_MS`，新增 `elapsedLabel`，`pollJob` 跟随到终态并显示 `Job <status> · <id 前 8 位> · 已用时`。
- `packages/python/llm/src/paper_llm/cache.py`：`put` 写 `mark.model_dump(exclude_none=True)`；新增 `_stored_mark` 在装载时丢弃 null 属性；`TRANSLATION_CACHE_VERSION` 保持 `"1"`，注释说明为何 null 归一化不构成版本变更。
- 测试：`packages/python/pdf-pipeline/tests/test_semantic.py::test_repeated_unresolved_citation_is_one_issue`（同一节点内 `[99]` 两次 → 1 条 Issue、id 唯一；在旧实现上失败）、`apps/web/src/import-panel.test.ts::bootImportPanel > keeps following a slow job instead of giving up on the client`（假时钟推进 15 分钟、400 次轮询后 `succeeded` → `load()` 恰好一次；在旧实现上失败）、`packages/python/llm/tests/test_cache.py`（带 mark 的行写出后重新装载可读回同一 marks；历史含显式 null 的行仍可命中——两者在旧实现上均失败）。既有面板用例「提交后必定先显示 `Job submitted`」因运行中状态行现在会改写文本而删除该断言，其余断言不变。
- `tests/golden/smoke/semantic.json`：8 处 provenance `producerVersion` 更新（见决策 2）。
- 文档：`docs/architecture/reader.md` / `reader.en.md`（导入面板轮询语义）、`docs/architecture/semantic-document.md` / `.en.md`（Issue 身份与 id 唯一是发布前提）、`docs/architecture/storage.md` / `.en.md`（缓存行的 mark 规范形与读侧 null 归一）。
- `tests/e2e/product-import.spec.ts`：`#import-status` 的 `Job submitted` 断言改为 `Job …` 前缀（提交行现在会在一个轮询周期内被进度行改写，具体文案已由 vitest 单测覆盖）。
- 验证：`uv run pytest -m "not e2e and not slow"` 558 passed / 5 deselected；`uv run pytest tests/golden -m golden` 通过；`pnpm exec vitest run` 59 passed（10 文件）；`just test-e2e` 14 passed；`just benchmark` 报告 `unchanged (all metrics within tolerance)`；`just check-fast` 通过（fmt/lint/typecheck/test-unit/schema/docs-fast/latex-check）。
- 真实论文复验（同一浏览器会话，全部用户操作在浏览器内）：修复后重跑同一 workspace，作业 3 秒 `succeeded`（SEMANTIC 因版本升级重跑、TRANSLATE/RENDER 产物字节不变被跳过、INDEX 首度成功），面板跟随到终态并就地换到修订 `66b6115c`；Source 1/11 页 ↔ Target 1/14 页，158 个 linked region，双向跳转跨页正常（target→source、source p4→target p4）；Inspector 显示原文/译文/锚点/置信度；Inspector 的 `Re-translate node` 在 18 秒内完成真实 provider 单节点重译并发布修订 `1d415311`（该路径也读同一个缓存文件，修复前它会直接抛校验错）。发布产物 `semantic.json` 43 条 Issue、id 全唯一（修复前 44 条含一组重复）。
- 遗留（本次验收观察到、未修，按现象归档）：真实论文上 36 条 `CITATION_RESOLUTION` WARNING（参考文献 40 条中只恢复出 12 条 `BIBLIOGRAPHY_ENTRY`，导致多数 `[n]` 未解析）；6 条 `SOURCE_MAPPING` 脚注告警（脚注文本被并入正文段落）；公式片段 `1 dk`、表注片段 `positional embedding instead of sinusoids` 被判为 HEADING；结果表行被折叠成 PARAGRAPH；图 1 图注渲染成 `Figure 1: 图 1: Transformer——模型架构。`（源 PDF 该行文本抽取本身重复交错："Figure 1:Figure The1:Transformer - model architecture."）。另一条与本次修复无关的复现路径：`just viewer-fixture` / `serve-reader` / `test-e2e` 在夹具 PDF 被重新编译（字节变化）后会因 `WorkspaceSourceMismatchError` 失败，需要先删除 `apps/web/.viewer-fixture` 或让 recipe 接受源变化（本次按前者的报错提示处理，未改 recipe）。
