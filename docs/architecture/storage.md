# 存储

[中文](./storage.md) | [English](./storage.en.md)

持久对象存储、制品布局与数据集托管**有意未决**；本地 Project / Document Workspace 约定已由 [M8 初版批次 A](../development/m8.md) 收口，见下。

## 本地 workspace（M8 批次 A，已收口）

`run_pipeline(source_pdf, out_dir)` 把 `out_dir` 变成一个**可恢复的本地 workspace**。目录布局：

```text
<workspace>/
  workspace.json          # ad-hoc 清单（与 probe.json 同类，不进冻结 schema）
  source.pdf              # INGEST 保留的源 PDF 字节
  physical.json …         # 各阶段 canonical JSON 产物
  probe.json              # 探测 + routing 诊断（ad-hoc）
  evidence-bundles.json   # 各 provider bundle 的 ad-hoc 持久化
  resources/              # 图像与 figure PDF fragment
  build/                  # LaTeX 编译产物（target.pdf），非清单产物
  viewer/data/            # viewer revision（沿用既有发布事务）
```

### 阶段与提交协议

阶段枚举：`INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC → TRANSLATE → RENDER → INDEX`（`pdf_pipeline.workspace`）。

- 每阶段在 `workspace.json` 记录：status、产物相对路径 + sha256、producer 版本、输入指纹（生产者版本 + 上游产物哈希）。
- 提交顺序：产物先写入 `.staging/`，逐文件原子 replace，最后原子重写 `workspace.json`——清单是**唯一提交指针**。
- 恢复：`stage_completed` 为真（COMPLETED + 产物哈希校验通过 + 输入指纹与上游记录一致）才跳过；否则重跑该阶段。中断后重启只重跑未完成阶段；半写入目录永远不会被当成成功。
- 源绑定：manifest 的 `sourceFingerprint` 锁定源 PDF；未知 `workspaceVersion` 与外来源 PDF 一律明确报错（迁移属批次 E）。

权威实现：`packages/python/pdf-pipeline/src/pdf_pipeline/workspace.py` 与 `pipeline.py` 的阶段 runner；决策理由见 Agent Note `2026-09-12-m8-batch-a-workspace-stages`。

### 当前边界

- `workspace.json` 是 ad-hoc 文件，schema 变更不走 `just schema` 冻结流程。
- 翻译配置变化导致的阶段失效与跨配置缓存键属批次 C；本版恢复只按上游产物哈希判断。
- viewer revision 发布沿用 `_publish_viewer_revision` 事务，不在清单内逐文件追踪。

## 仍未决

持久对象存储、多机共享、数据集托管。未来的外部数据集系统需要 testing 或 architecture Agent Note。

保持 Git 历史精简。不要提交大型 PDF 语料。
