# 测试

[中文](./overview.md) | [English](./overview.en.md)

## 分类

| 种类 | 含义 |
| --- | --- |
| unit | 小而确定的行为 |
| integration | 多个内部组件 |
| golden | 规范的结构化期望输出 |
| regression | 已观察缺陷的复现 |
| e2e | 产品级流程 |
| rendering | SemanticDocument → LaTeX → PDF |
| benchmark | 性能与内存 |

## 命令

`just test`、`just test-unit`、`just test-integration`、`just test-golden`、`just test-e2e`、`just latex-smoke`。

空类别打印 `no <kind> tests currently defined`，而不是因配置错误而闭合失败。

核心生产 Python 的覆盖率目标约 80%。关键 SemanticDocument、映射与序列化路径以后需要更高。

见 [`fixtures.md`](fixtures.md)、[`golden.md`](golden.md)、[`rendering.md`](rendering.md)。
