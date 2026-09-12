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
| benchmark | 语料质量回归（`just benchmark` 对比 `tests/benchmark/baseline.json`） |

## 命令

`just test`、`just test-unit`、`just test-integration`、`just test-golden`、`just test-e2e`、`just latex-smoke`、`just benchmark`。

空类别打印 `no <kind> tests currently defined`，而不是因配置错误而闭合失败。

PR CI 的 Python job 在编译夹具与 `just test-python` 之后运行 `just benchmark`；缺失夹具、可测指标变 null、指标下降或 ERROR/FATAL 增加会使门禁失败。不要为转绿改 baseline。详情见 [golden.md](golden.md) 与 [M8 准入](../development/m8.md)。

核心生产 Python 的覆盖率目标约 80%。关键 SemanticDocument、映射与序列化路径以后需要更高。

见 [`fixtures.md`](fixtures.md)、[`golden.md`](golden.md)、[`rendering.md`](rendering.md)。
