# Agent Note: M8 准入收口与初版范围

Status: implemented

[中文](./2026-09-12-m8-admission-closeout.md) | [English](./2026-09-12-m8-admission-closeout.en.md)

## 问题

进入 M8 前的三项 PRD 表面已经有实现与审查修复，但进度文档把「已实现」「合成夹具通过」「真实工具验证通过」写成同一句「已收口」。`just benchmark` 只在 nightly 单独重装 TeX 后运行，未进入 PR CI / `CI / gate`。真实 MinerU / Docling / GROBID 输出未沿 adapter → normalize/fusion → semantic 验证。若不裁定 M8 初版范围，路线图仍会把 Typst、HTML、Analysis Layer 当成同一 Milestone 的强制项。本 note 补充 [PRD 过滤 roadmap 延期项](./2026-09-12-prd-filters-roadmap-deferrals.md)、[可选真实 parser 依赖](../architecture/2026-09-12-optional-parser-adapters.md)、[区域级标注真值](../architecture/2026-09-12-region-level-layout-truth.md)、[Figure PDF fragment](../architecture/2026-09-12-figure-pdf-fragment.md)、[M8 前审查修复](../bug-fix/2026-09-12-m8-pre-review-repairs.md)，不改写其历史决策句。

## 决策

1. **准入分级，禁止混用。** 当前态只允许三种标签：已实现、合成夹具通过、真实工具验证通过。三项表面的权威清单与是否阻塞 M8 见 [`docs/development/m8.md`](../../../../docs/development/m8.md)。
2. **PR CI 运行 `just benchmark`。** Python reusable workflow 在已有 `just latex-smoke` 与 `just test-python` 之后调用同一 recipe；`CI / gate` 依赖 python job，因此质量回归会挡住合并。`just ci` 把 `benchmark` 列为依赖。Nightly 复用 `ci-python.yml`，删除重复安装 TeX 的独立 benchmark job。禁止为转绿重置 baseline 或更新 golden。比较器必须让缺失夹具、可测指标变 null、指标下降、ERROR/FATAL 增加失败；校准准确率仍是 diagnostic。这是对 [Git 与 CI 治理](./2026-09-03-git-and-ci-governance.md) 后果的事实更新，不改变主干开发与分生态 workflow 决策。
3. **真实 parser 缺口如实记录。** 合成 dump 保留为契约测试，并补 adapter → normalize/fusion → semantic 链路。2026-09-12 本机未安装 MinerU/Docling，无 `GROBID_URL`，不伪造录制。生产 capability registry 仍是 `mock` / `docling-sim` / `grobid-sim`。把 registry primary 换成真实 parser、以及可配置替换入口，属 M8 批次 E，不是本轮范围。
4. **M8 初版范围。** 初版只做本地 workspace 持久化、任务恢复、增量重处理、缓存、specialist 失败隔离、旧 workspace 兼容/迁移或明确拒绝、parser 接入配置。Typst、HTML、Analysis Layer 按 PRD §44 / R7–R8 为后续扩展。不重新引入扫描 OCR、字符级 mapping、双栏译文、Annotation、独立 MathML。`paragraphLabelRecall` / `headingLabelRecall` 保持布局标签召回含义。分批计划的权威文本是 [`docs/development/m8.md`](../../../../docs/development/m8.md)。

## 考虑过的替代方案

- 把「三项已落地」继续写成 M8 准入：会把合成契约当成真实 parser 端到端，违反审查要求。
- 为凑真实 dump 手写「像官方输出」的 JSON 并标成录制：伪造证据。
- 把 MinerU/Docling/GROBID 加进默认依赖或 CI：违反可选 extras 与重型原生库决策。
- 等真实工具跑通再进 M8：会把本地 workspace / 缓存 / 恢复这些 PRD Local-first 缺口继续挂在 parser 活服务上。
- 在 PR CI 再写一套独立 TeX 安装跑 benchmark：重复 `ci-python.yml` 已有的 smoke。

## 后果

- 准入结论：可以开始 M8 初版 A–D；真实 parser 工具验证未通过，阻塞生产 registry 替换，不阻塞本地 workspace 工作。
- 当前态：[`docs/development/m8.md`](../../../../docs/development/m8.md)、[`docs/development/roadmap.md`](../../../../docs/development/roadmap.md)、README、parser 契约与夹具页。
- dump 分级见 `tests/fixtures/parser-dumps/provenance.json`。
