# HTTP API

[中文](./api.md) | [English](./api.en.md)

API 应用是 `apps/api` 下的运行时入口（stdlib `ThreadingHTTPServer`，仓库有意不引入 web 框架）。产品 HTTP 契约 **有意未决**，但以下端点已落地：M6 reader API（见 [`reader.md`](reader.md)）与 M8 批次 B 的 Job API（记录格式与状态机见 [`storage.md`](storage.md) 的「任务与 Job 记录」）。业务逻辑在 `paper_api/retranslate.py`、`paper_api/jobs.py`、`paper_api/workspaces.py`、`paper_api/uploads.py` 与 `paper_api/status.py`，`__main__` 只做接线。

| 路径 | GET | POST | PUT / DELETE / PATCH |
| --- | --- | --- | --- |
| `/`、`/health`、`/api/health` | 200 `{"status":"ok","service":"api"}` | 404 | 404 |
| `/api/retranslate` | 405 | 200 / 400 / 408 / 409 / 413 / 503 | 405 |
| `/api/jobs` | 200 列表 | 202 提交（400 / 413 / 500） | 405 |
| `/api/jobs/<id>` | 200 / 404 | 405 | 405 |
| `/api/jobs/<id>/retry` | 405 | 202 / 404 / 409 | 405 |
| `/api/workspaces` | 200 列表 | 405 | 405 |
| `/api/workspaces/open` | 405 | 200 / 400 / 404 / 500 | 405 |
| `/api/uploads` | 405 | 200 / 400 / 413 | 405 |
| `/api/status` | 200 | 405 | 405 |
| 其它路径 | 404 | 404 | 404 |

- `/api/jobs` 的提交 body：`source` 与 `workspace` 必填、`viewerDataDir` 可选（省略或 `null` ⇒ 取服务端自己的 `--data-dir`，即本地 viewer 读取的目录——M8 批次 F）；显式值与另外两个字段都必须是**绝对路径**，且 `source` 必须已存在（否则 400）。成功响应 `202 {"ok": true, "job": <记录>}`，`job.status == "queued"`、`job.attempt == 1`，且记录携带**生效的** `viewerDataDir`。
- `/api/jobs/<id>/retry` 不读 body；非 `failed` 状态返回 `409`，未知 id 返回 `404`。
- `GET /api/workspaces`：`200 {"ok": true, "workspaces": [...]}`；每项是 workspace 摘要（`name` / `path` / `workspaceVersion` / `stages`（8 个阶段名全在，缺记录为 `pending`）/ `complete` / `updatedAt` / `error`）加 `publication.current`（该 workspace 是否就是当前 manifest 绑定的那一个）。枚举的是 `discover_workspaces()`：`<jobs-root>/workspaces/*/workspace.json` 加上 API 自己的 workspace，按 manifest mtime 降序。坏清单不抛错，只让该行 `error` 非空、`complete` 为 false。
- `POST /api/workspaces/open`：body `{"workspace": "<绝对路径>"}`；非法 JSON、缺字段、非绝对路径一律 400；目录下没有 `workspace.json` 返回 404；workspace 不可读（清单缺失或损坏、版本不受支持、源 PDF 不匹配、阶段未提交）返回 400；其它异常 500；成功 `200 {"ok": true, "revision": <id>}`。服务端把该 workspace **已提交的产物**原样重发布到自己的 `--data-dir`（`republish_workspace_viewer`：不跑 stage、不写 workspace），见[存储](storage.md#演示控制台)。
- `POST /api/uploads`：body 即 PDF 字节，上限 `MAX_UPLOAD_BYTES`（64 MiB）；`X-Upload-Name` 必填且必须以 `.pdf` 结尾（缺头或非 PDF 名都是 400）；`Content-Length` 声明超限时不读 body 直接 413；收到的前 5 字节必须是 `%PDF-`、总字节不能为 0（否则 400）。成功 `200 {"ok": true, "path": <inbox 绝对路径>, "workspace": <服务端推导的 workspace 绝对路径>, "bytes": <n>, "sha256": <hex>}`；文件名与 workspace 名都由「文件名 slug + 内容摘要前 8 位」派生，因此同名同内容的重复上传复用同一文件与同一 workspace。
- `GET /api/status`：`200 {"ok": true, "api": <health payload>, "worker": {...}, "jobs": {...}, "viewer": {...}}`。`worker` 的键固定为 `present` / `alive` / `pid` / `startedAt` / `updatedAt` / `ageSeconds` / `concurrency` / `running`（无心跳或心跳不可解析时相应字段为 `null`，`running` 恒为整数），`alive` 的判据是心跳年龄 `<= HEARTBEAT_STALE_S`（15 s）。`jobs` 是 `queued` / `running` / `succeeded` / `failed` 计数加 `oldestQueuedAt`（无 queued 时为 `null`）。`viewer` 取当前 manifest 的 `revision` 与 `workspace`，manifest 缺失或损坏时为 `null`。
- 读写边界：客户端只指定**读来源**。`POST /api/workspaces/open` 的 workspace 路径与 `POST /api/uploads` 的字节都只决定读什么；写目标全部由服务端拥有——`--data-dir`（viewer 数据目录）与 `<jobs-root>/inbox`（上传收件箱）。这与 `/api/retranslate` 按当前绑定选择文档、不接受客户端写路径是同一条规则。
- JSON body 上限与 `/api/retranslate` 共用 `MAX_BODY_BYTES`（4096），超限 413；`/api/uploads` 不走这条路径（流式接收，用自己的 64 MiB 上限）。
- 方法或路径不匹配时：已知路径给 `405 {"ok": false, ...}`，未知路径给 `404`。
- 端点的 `pdf_pipeline` 导入都是惰性执行，API 启动不加载 pdfium。

命令行：`python -m paper_api [--workspace DIR] [--data-dir DIR] [--jobs-root DIR] [--port N]`，`--jobs-root` 默认 `.jobs`。

更广的契约存在时将作为 OpenAPI 放在 `schemas/api/`。`just schema` 目前报告尚未定义 OpenAPI 文档。

## 重译的文档绑定

浏览器向 `/api/retranslate` 提交 `{nodeIds, revision}`。服务端按当前 Viewer manifest 的 workspace 绑定定位文档；导入第二份文档后无需重启 API。客户端不传 workspace 路径。revision 类型错误返回 400；当前 revision 不匹配，或重译计算期间被另一发布替换，返回 409，后者不会提交此次 workspace 更新。旧客户端可省略 revision；旧 manifest 无 workspace 绑定时回退启动参数 `--workspace`。锁与发布契约见[存储](storage.md)。
