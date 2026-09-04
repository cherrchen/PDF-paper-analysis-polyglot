# 层职责边界

[中文](./layer-responsibility.md) | [English](./layer-responsibility.en.md)

权威定义：[`docs/architecture/document-architecture.md`](../architecture/document-architecture.md) §1、§3、§5、§13、§25。

## 四层模型

| 层 | 回答的问题 | 不得包含 |
| --- | --- | --- |
| PhysicalDocument | PDF 客观存在什么 | 阅读顺序推断、章节语义 |
| LayoutDocument | 页面视觉如何组织 | `method_section = true` 等语义标签 |
| SemanticDocument | 文档逻辑是什么 | `bbox`、`page`、`column` |
| RenderDocument | 目标内容如何呈现 | 源 PDF 硬性排版合同 |

## 永久禁止

```text
SemanticParagraph.bbox / .page / .column
LayoutRegion.method_section = true
```

## 层间连接

层与层之间只通过 Binding / Anchor 映射，不共享实现类型，不用页码或 bbox 作为 SemanticNode 持久身份。

## 证据与派生

- 第三方 parser 输出只能是 Evidence，经 Adapter 进入内部 Recovery。
- Translation / Analysis / Annotation 是 Derived Layer，不修改 Source SemanticDocument。
- 源 layout 是理解证据，不是译文 PDF 的排版合同。
