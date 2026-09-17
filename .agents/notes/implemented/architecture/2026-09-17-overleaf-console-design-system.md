# Agent Note: Overleaf 风格控制台设计系统

Status: implemented

[中文](./2026-09-17-overleaf-console-design-system.md) | [English](./2026-09-17-overleaf-console-design-system.en.md)

## 问题

M2 走通骨架留下的控制台视觉语言是自绘的：slate-blue 边框（`#234f68` / `#afbec7` / `#9db6c2`）、Charter 衬线标题、靠 `linear-gradient` 在 1560px 版面上画出的中线折痕、重投影阴影、从头到尾的 monospace，以及一个橙色（`#e4572e`）选中色。用户给出 Overleaf 截图，要求控制台向它的观感看齐：扁平浅灰 chrome、白色表面、绿色主操作、sans-serif UI 字体，monospace 只留给标识符与路径。

本轮范围由用户明确为**只换皮**：DOM 结构、两栏 `#panes` grid、`#surface-tabs` 行，以及右侧**悬浮** `#surface-panels` 抽屉（含其全部几何）都不动——[2026-09-16 的四表面 note](./2026-09-16-demo-console-surfaces.md) 里「抽屉不占 PDF 宽度」的决策继续有效，本轮既不引入 Overleaf 式左栏，也不把抽屉改成占宽列。UI 只新增一个控件：masthead 里的绿色主按钮 `#open-upload`，位置与颜色对齐 Overleaf 的 Recompile/Share 位置。

## 决策

1. **调色板逐值抄自 Overleaf 已发布样式表，且只有一处家。** 色阶与语义 token 全部来自 `https://cdn.overleaf.com/stylesheets/main-style-476eb7ca577de65f3a7b.css`（2026-09-17 抓取），沿用上游 token 名（`--green-*` / `--neutral-*` / `--blue-*` / `--red-*` / `--yellow-*` 与 `--bg-light-*` / `--bg-accent-01` / `--content-*` / `--border-*`），因此控制台与参照物可以逐行 diff。该块是 `viewer.css` 里唯一的颜色真源：`#rrggbb` 只允许出现在 `:root` 内，其余一律 `var(--…)`，或由这些 token 派生的 `rgb(… / …)`（两处半透明覆盖与两处阴影）。字体栈与 `--radius` / `--shadow-*` / `--focus-ring` 是控制台本地补充，没有上游对应物。
2. **布局几何不变。** 抽屉仍是 `top: 0; right: 0; bottom: 3.5rem; width: min(360px, 34vw)`、`z-index: 6`、容器 `pointer-events: none`；`.page-scroll` 仍是 `max-height: 72vh` 且不加内外边距/边框；`.page-stage` 保持 `overflow: hidden`，canvas 仍是 `width: 100%; height: auto` 且**只有一个** 1px 边框——fit-width 与 `inset: 0` 的 overlay 对齐都依赖这些事实，因此换皮只改颜色、圆角、阴影与字体。`main` 仍是 `min(1560px, 100%)`，只去掉竖向留白与衬线标题规则。
3. **字体分工。** UI 用系统 sans 栈（不下载 webfont），monospace 只用于标识符、路径、页码与几何读数（`#source-page` / `#target-page`、`#inspector-node-id`、`#inspector-anchors`、`#viewer-status`、select 的 path 与各 updatedAt）；Inspector 的正文（`#inspector-source-text` / `#inspector-translation`）用 `--text-md` 的 sans，因为那是被阅读的文档文本而不是标识符。
4. **masthead 是 sticky 白底，主按钮与 tab 共用一条状态机。** `.masthead` 改成 `grid-template-columns: auto 1fr auto`（`.brand-mark` 品牌块 / `.brand-text` / `.masthead-actions`），`#open-upload` 只做一件事——`SurfaceTabs.open("upload")`——不复制打开逻辑，也不加 `aria-controls`（`#panel-upload` 的关系已由 `#tab-upload` 承担）。`SurfaceTabs.open` 是幂等的，所以面板已打开时再点按钮什么都不做；关闭仍走 `#tab-upload`。窄屏（≤ 840px）时 masthead 退成 `auto 1fr` 两列、`.masthead-actions` 独占一行（取代旧的 `display: block` 堆叠）。
5. **绿色只表示主操作与选中态。** 主按钮（`#open-upload` / `#import-submit` / select 的 `.select-open` / history 的 `.history-open` / `#retranslate-button`）共用一条 `:is(…)` 规则，靠 `#import-submit` / `#retranslate-button` 带进来的 id 权重压过 `.surface-panel button` / `.inspector-section button` 的次级按钮样式，不必逐个按钮重写；tab 的 `aria-selected="true"` 与 `aria-pressed="true"` 的 region 也用同一绿色。悬浮 region 的常态/hover 用蓝色，选中才转绿——橙色的「选中」含义消失。
6. **两个 checkbox 自绘但仍是原生 `input`。** `appearance: none` + 勾选态绿色背景 + `box-shadow` focus 环；尺寸 `0.9rem`，绝不 `display: none`、`opacity: 0` 或零尺寸盒——`#inspector-toggle` 与 `#sync-scroll` 由 e2e 直接 `check` / `uncheck`，命中点必须是 input 自身。

## 考虑过的替代方案

- **改成 Overleaf 式左栏 + 占宽面板的完整外壳。** 最贴参照物的结构，但它直接推翻 2026-09-16「抽屉不占 PDF 宽度」的决策，而本轮目标是观感对齐；用户已明确选择只换皮，所以左栏留待真正需要时另开 note。
- **保留 M2 的 slate-blue 调色板，只调整字体与阴影。** 改动最小，但用户给截图的目的就是要那套绿色主操作与浅灰 chrome，保留旧色板等于不执行。
- **加载 Noto Sans / Inter webfont。** 能逐字形对齐 Overleaf，代价是新增网络依赖与首屏字体切换（截图之外的收益很小）；系统 sans 栈让渲染平台各按其默认 UI 字体渲染。
- **深色主题 / `prefers-color-scheme` 变体。** 参照物只有浅色，且 token 层一旦分裂成两套就必须同时维护 region 覆盖色与抽屉半透明底；本轮只做浅色，token 命名已按上游留出扩展位。
- **给 `#open-upload` 加上打开/关闭的 toggle 语义。** 会让按钮与 `#tab-upload` 的状态源分叉；`SurfaceTabs` 是唯一状态源，按钮只做转发，重复点击是 no-op。

## 后果

- `apps/web/src/viewer.css`：`:root`（调色板 + 字体/尺寸/圆角/阴影 token）、页面 chrome、栏与抽屉、tab 与 checkbox、面板与 Inspector 全部重写；`box-shadow`、`linear-gradient` 折痕、衬线字体栈、`opacity` 禁用态与橙色选中色全部删除；`.page-scroll` / `.page-stage` / `#surface-panels` 的几何声明逐字保留。
- `apps/web/index.html`：masthead 块新增 `.brand-mark`（内联 SVG，`aria-hidden="true"`）与 `#open-upload`，其余字节不变，全部既有 id 保留。
- `apps/web/src/main.ts`：`init()` 末尾一处 `#open-upload` 点击监听转发到 `tabs.open("upload")`。
- e2e：`tests/e2e/console-surfaces.spec.ts` 新增一条断言——点 `#open-upload` 后 `#panel-upload` 可见且 `#tab-upload` 为 `aria-selected="true"`，再点 `#tab-upload` 关闭。
- Vale 词表：`.vale/styles/config/vocabularies/Paper/accept.txt` 新增 `Noto` / `Overleaf` / `Overleaf's` / `monospace` / `reskin` / `select's` / `webfont` / `webfonts`——这些词此前被 `Vale.Spelling` 记为 error（`just docs` 因此失败）。
- 文档：控制台视觉层写进 [`reader.md`](../../../../docs/architecture/reader.md)（与英文伴侣 `reader.en.md`）的布局段，几何事实逐条保留。
- 已知代价：系统 sans 栈不等于 Overleaf 的 Noto Sans，字形有差；调色板里的 `--green-20` / `--green-40` / `--neutral-05` / `--blue-10` / `--red-40` / `--yellow-*` 目前没有消费者，保留是为了让 token 块与上游逐行可比。

部分取代 [2026-09-16 四表面 note](./2026-09-16-demo-console-surfaces.md) 的视觉语言：其决策 1–8（四表面划分、悬浮抽屉、fit-width 与比例滚动、upload/select/status 行为、读写边界）仍然有效。M6 的跳转与 overlay 契约见 [M6 note](../feature/2026-09-11-m6-bidirectional-reader.md)。
