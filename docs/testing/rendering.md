# 渲染测试

[中文](./rendering.md) | [English](./rendering.en.md)

默认不要比较原始 PDF 字节。对象顺序与元数据可能变化。

校验层级：

1. LaTeX 编译成功
2. PDF 页数
3. 文本抽取健全性
4. 期望的结构元数据
5. 带容差的视觉回归，仅在存在稳定基线时

`just latex-smoke` 覆盖一等夹具的 (1)。像素差尚未实现。
