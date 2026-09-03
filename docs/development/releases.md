# 发布

[中文](./releases.md) | [English](./releases.en.md)

架构不稳定期间项目为 `v0.x`。遵循语义化版本。

- 标签：`v0.y.z`
- 变更日志：[`CHANGELOG.md`](../../CHANGELOG.md) 在发版时更新，不在每次提交时更新
- 制品：尚未发布到 PyPI、npm 或 crates.io
- 自动化：打标签可以从 changelog 创建 GitHub Release。在可分发包存在之前，向注册表发布不在范围内

制品存在时，通过明确的 process Agent Note 加入校验和、SBOM 与证明。现在不要虚构注册表密钥。
