# HTTP API

[中文](./api.md) | [English](./api.en.md)

API 应用是 `apps/api` 下的运行时入口（stdlib `ThreadingHTTPServer`，仓库有意不引入 web 框架）。产品 HTTP 契约 **有意未决**，但以下端点已落地：M6 reader API（见 [`reader.md`](reader.md)）与 M8 批次 B 的 Job API（记录格式与状态机见 [`storage.md`](storage.md) 的「任务与 Job 记录」）。业务逻辑在 `paper_api/retranslate.py` 与 `paper_api/jobs.py`，`__main__` 只做接线。

| 路径 | GET | POST | PUT / DELETE / PATCH |
| --- | --- | --- | --- |
| `/`、`/health`、`/api/health` | 200 `{"status":"ok","service":"api"}` | 404 | 404 |
| `/api/retranslate` | 405 | 200 / 400 / 408 / 409 / 413 / 503 | 405 |
| `/api/jobs` | 200 列表 | 202 提交（400 / 413 / 500） | 405 |
| `/api/jobs/<id>` | 200 / 404 | 405 | 405 |
| `/api/jobs/<id>/retry` | 405 | 202 / 404 / 409 | 405 |
| 其它路径 | 404 | 404 | 404 |

- `/api/jobs` 的提交 body：`source` 与 `workspace` 必填、`viewerDataDir` 可选（省略或 `null` ⇒ 取服务端自己的 `--data-dir`，即本地 viewer 读取的目录——M8 批次 F）；显式值与另外两个字段都必须是**绝对路径**，且 `source` 必须已存在（否则 400）。成功响应 `202 {"ok": true, "job": <记录>}`，`job.status == "queued"`、`job.attempt == 1`，且记录携带**生效的** `viewerDataDir`。
- `/api/jobs/<id>/retry` 不读 body；非 `failed` 状态返回 `409`，未知 id 返回 `404`。
- body 上限与 `/api/retranslate` 共用 `MAX_BODY_BYTES`（4096），超限 413。
- 方法或路径不匹配时：已知路径给 `405 {"ok": false, ...}`，未知路径给 `404`。
- 端点的 `pdf_pipeline` 导入都是惰性执行，API 启动不加载 pdfium。

命令行：`python -m paper_api [--workspace DIR] [--data-dir DIR] [--jobs-root DIR] [--port N]`，`--jobs-root` 默认 `.jobs`。

更广的契约存在时将作为 OpenAPI 放在 `schemas/api/`。`just schema` 目前报告尚未定义 OpenAPI 文档。

## 重译的文档绑定

浏览器向 `/api/retranslate` 提交 `{nodeIds, revision}`。服务端按当前 Viewer manifest 的 workspace 绑定定位文档；导入第二份文档后无需重启 API。客户端不传 workspace 路径。revision 类型错误返回 400；当前 revision 不匹配，或重译计算期间被另一发布替换，返回 409，后者不会提交此次 workspace 更新。旧客户端可省略 revision；旧 manifest 无 workspace 绑定时回退启动参数 `--workspace`。锁与发布契约见[存储](storage.md)。
