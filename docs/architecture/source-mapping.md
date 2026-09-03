# 源映射

[中文](./source-mapping.md) | [English](./source-mapping.en.md)

映射架构见 [`document-architecture.md`](document-architecture.md) 第 18–21、33 节。

三层映射链：

```text
PhysicalLayoutBinding → SourceAnchor → SourceSemanticBinding
```

支持 N Layout ↔ N Semantic（如跨栏段落）。双向跳转以 Heading、Paragraph、Figure 等 semantic block 为单位，不以 Section 为主要几何单位。

v0.1 不做字符级 mapping。`SourceFragment` 仅 `LayoutRegionRef`。
