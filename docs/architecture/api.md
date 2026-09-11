# HTTP API

[中文](./api.md) | [English](./api.en.md)

API 应用是 `apps/api` 下的运行时入口（stdlib `ThreadingHTTPServer`，仓库有意不引入 web 框架）。产品 HTTP 契约 **有意未决**；当前唯一落地的是 M6 reader API：`GET /api/health` 与 `POST /api/retranslate`（局部重渲染，见 [`reader.md`](reader.md)）。业务逻辑在 `paper_api/retranslate.py`，`__main__` 只做接线。

更广的契约存在时将作为 OpenAPI 放在 `schemas/api/`。`just schema` 目前报告尚未定义 OpenAPI 文档。
