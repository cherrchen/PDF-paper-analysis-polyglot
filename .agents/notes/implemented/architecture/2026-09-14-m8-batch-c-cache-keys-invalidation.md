# Agent Note: M8 批次 C 阶段缓存键、失效传播与局部重跑

Status: implemented

[中文](./2026-09-14-m8-batch-c-cache-keys-invalidation.md) | [English](./2026-09-14-m8-batch-c-cache-keys-invalidation.en.md)

## 问题

批次 A 的阶段状态只把「producer 版本 + 上游产物 sha256」折进 `inputFingerprint`，批次 B 的 Job 层不持有任何指纹。因此换 capability registry、换 parser dump、改翻译配置都不会使 TRANSLATE/EVIDENCE 失效：workspace 会静默复用按旧配置生成的产物，而 `docs/architecture/storage.md` 明确把「翻译配置变化导致的阶段失效与跨配置缓存键」判给批次 C。翻译缓存（`paper_llm.cache.TranslationCache`）的键虽含 node/content/locale/model/endpoint/terminology/prompt/context，却没有任何「键派生规则版本」：键材料语义变更后旧行会被静默读取并当成命中。此外没有显式局部重跑入口（重跑某个阶段只能删整个 workspace），源 PDF 变化只有「报错」一条路径。

三条验收：重译不重跑 physical/layout/semantic；parser dump、registry、源 PDF 字节变化使依赖下游失效；缓存不跨配置、版本、源文件误命中。

## 决策

1. **阶段配置折进既有 `inputFingerprint`，不新增清单字段，`WORKSPACE_VERSION` 保持 `0.1.0`**。`input_fingerprint(producer_version, inputs, config)` 的 material 变为 `{producerVersion, inputs(sorted), config(sorted)}`；`WorkspaceManager` 持有 `stage_configs`，`commit_stage` 不再接收 `inputFingerprint`，改为内部由 `make_stage_record` 计算（上游记录 + 阶段配置）。字段名与清单键名不变。理由：键材料扩展只会让旧 workspace 全阶段重跑一次（安全方向），而升 `WORKSPACE_VERSION` 会直接**拒绝**既有 workspace——版本迁移/拒绝的边界属批次 E，不在本批次改判。新增字段则会让「空配置」与「未记录配置」在清单里不可区分，且迁移规则同样属批次 E。
2. **`pipeline.stage_config_inputs(config, source_bytes)` 是唯一真源**，返回 8 个阶段各自的配置映射；`run_pipeline` 与 `rerender_workspace` 都用它构造 `WorkspaceManager`。两处共用同一入口，rerender 写的 TRANSLATE/RENDER 记录才能与下一次 `run_pipeline` 的判定一致（否则重译后必然全链重跑）。
3. **公共项 `schemaVersion` + `pipelineVersion`**：任何阶段代码或 canonical schema 变化都让全阶段失效。粒度粗（改 INDEX 也会重跑 INGEST），但方向安全、无需为每个阶段维护版本常量。
4. **registry 与 parser dump 用内容摘要，不用版本常量**：两者都是手改数据；用版本常量会在「改了却忘了升版本」时静默复用。`registry_fingerprint()` 与 `template_fingerprint()` 以模块名导入 `pipeline`，测试可 monkeypatch。
5. **parser dump 按 adapter 自己的解析规则定位**（`resolve_dump_path(provider, fingerprint, env_path)`，与真实 adapter 同一函数），值取文件 sha256；无 dump 记 `"none"`，读取失败记 `"unreadable"`。另有 `liveEnv:MINERU_CMD` / `liveEnv:DOCLING_CMD` / `liveEnv:GROBID_URL` 三个字面量。**三个真实 adapter 一律入键，不按 routing 收窄**：routing 需要 probe，收窄会把「该阶段实际会读的 dump」判断错；过度失效只多跑一次，误命中会静默陈旧。
6. **翻译配置入键项限定为影响产物语义的部分**：`targetLocale`、`sourceLocale`、`providerModel`、`providerEndpoint`、terminology 文件字节。**排除** api key、`timeout_s`、`max_retries`、`cache_dir`——它们不改变产物内容，入键只会让无意义的配置调整触发重跑。`providerModel`/`providerEndpoint` 由 `_provider_identity()` 生产，与 `_build_translation_provider` 写进 `TranslationLayer.providerModel` 的值同源，避免「阶段配置」与「层身份」两个真源。
7. **源 PDF 变化默认保持「明确报错」**，另加显式 opt-in：`run_pipeline(..., accept_source_change=True)` / CLI `--accept-source-change` 重绑 `sourceFingerprint` 并丢弃全部阶段记录（不删除盘上旧产物：清单是唯一指针，各阶段重跑会覆写自己声明的路径）。默认报错是批次 A 已落地的安全语义，本批次不改默认。
8. **局部重跑是显式入口**：`run_pipeline(..., rerun_from=<stage>)` / CLI `--rerun-from <stage>` 在运行前 `WorkspaceManager.invalidate_from(stage)`（就地丢弃该阶段及 `STAGE_ORDER` 中其后所有记录 + 写清单）。只走 `pdf_pipeline` Python API + CLI，不动 `apps/`、`JobRecord` 形状与 Job API。
9. **SEMANTIC 提交前清空 `<ws>/resources/`**：该阶段的产物集合是 `_directory_artifacts(resource_dir, "resources")`，即「目录内所有文件」；不清空的话，换源或换 figure 集合后残留文件会被登记为新产物（并让下游把陈旧资源当当前输出）。`rerender_workspace` 不重新提取资源，不受影响。
10. **翻译缓存行带 `cacheVersion`（`TRANSLATION_CACHE_VERSION`，当前 `"1"`），该常量同时是键派生规则版本**：`_cache_key` 的 payload 增 `"version"`，`TranslationCache.__init__` 跳过版本不匹配的行（忽略、不迁移），`put` 写出该字段。不迁移是有意的：跨版本键材料不可比较，迁移等于猜测。
11. **键只算一次**：`translate_document` 的 RichText 分支算出 `cache_key` 后同时传给 `_translate_node`（缓存查/写）与 `_make_entry`（`TranslationEntry.cacheKey`），`_translate_table_content` 为每个 cell 算一次。`_make_entry` 因此退化为 `(semantic_node_id, content, cache_key, confidence, provider_model)`——key 由调用方给，它不再需要 context/kind/candidates 这些只为算 key 而传的参数。表节点的节点级键是整表内容/配置摘要而非缓存地址（表按 cell 缓存），这一语义写进 `_make_entry` docstring。

## 考虑过的替代方案

- **升 `WORKSPACE_VERSION` 到 `0.2.0`**：语义上「缓存键材料变了」确实像版本变化，但代价是把所有既有 workspace 判为不支持并直接拒绝，而批次 E 才是负责迁移/拒绝策略的批次；键材料扩展本身是安全方向（多跑一次，不会误命中）。
- **新增 `configFingerprint` 清单字段**：清单里就会出现「空配置」与「旧 workspace 未记录」两种同形的空值，判定必须靠版本或哨兵值，等于把问题推给批次 E；折进既有字段则旧 workspace 天然全阶段重跑一次。
- **每个阶段维护独立代码版本常量**：需要 8 个常量并在每次改阶段代码时手动升级，漏升即静默陈旧；`pipelineVersion` 粗粒度失效一次即可。
- **registry 用 `REGISTRY_VERSION` 常量**：registry 是 TOML 数据文件，改数据不会改代码；用内容摘要才能覆盖「改了忘升版本」。
- **按 routing 结果只把实际使用的 adapter 入键**：需要 probe（依赖 physical 产物），把键计算绑到运行期判定上；routing 变化本身还会改变 evidence 内容但可能不改变「用到哪些 dump」。
- **把 api key / timeout / retries 入键**：会把「运维参数调整」变成「整链重跑」，且 key 泄漏进清单文件。
- **源变化自动重绑（不报错）**：静默把 workspace 变成另一篇论文的产物集合；批次 A 已定「明确报错」，本批次只加 opt-in。
- **局部重跑只做 API、不做 CLI**：CLI 冒烟与运维都需要它，且 Job API 形状不在本批次范围内。
- **保留 `_make_entry` 自己算 key（两处各算一次）**：两次计算必须永远等价，等价性靠约定维持；共享一个 `cache_key` 让「entry 的键」与「命中的键」在类型层面绑定。
- **缓存行做版本迁移**：需要为每个历史键材料写转换器，而缓存是本地可重建的派生数据，忽略旧行只损失一次 provider 调用。

## 后果

- `WorkspaceManager.commit_stage` 不再接收 `input_fingerprint`；`_stage_inputs`（pipeline 私有）删除，其「上游未提交即报错」守卫移入 `WorkspaceManager._require_upstream_artifacts`（抛 `WorkspaceError`，消息不变）。新增 `make_stage_record`（供 rerender 事务复用同一套键计算）、`drop_stage_records`、`invalidate_from`、`_stage_config`。
- `open_or_create(source_bytes, *, accept_source_change=False)`：`_load_existing` 现在返回「源不匹配」而不是直接抛，由调用方决定报错或重绑。
- `pipeline.stage_config_inputs` / `_provider_identity` / `_file_digest` / `_parser_config_inputs` 为新增；`capabilities.registry_fingerprint`、`render_latex.template_fingerprint` 为新增公开函数；`paper_llm.cache.TRANSLATION_CACHE_VERSION` 为新增常量。
- CLI 新增 `--rerun-from` 与 `--accept-source-change`；`run_pipeline` 新增两个关键字参数（`apps/` 与 Job 层未改，沿用默认值即批次 B 行为）。
- 既有 workspace 首次运行会因键材料扩展而全阶段重跑一次；此后按新键判定。翻译缓存旧行被忽略一次，之后按新版本写入。
- 已落地的批次 A「清单写入失败还原内存记录」语义不变（`commit_stage` 的 previous/rollback 分支未动），仅记录构造方式改变。
- 验证：`test_workspace.py` 25 项、`test_pipeline_resume.py` 17 项、`test_rerender_workspace.py` 14 项、`test_cache.py`、`test_translation.py` 全绿；`just test-python`、`just check-fast`、`just test-golden`（`tests/golden/smoke/semantic.json` 未变）、`just docs-fast` 全绿；真实 `lualatex` CLI 冒烟：全量运行 → `--rerun-from translate`（前 5 阶段记录与产物哈希逐字节不变）→ 对第二个源 PDF 不带 flag 报 `WorkspaceSourceMismatchError`、带 `--accept-source-change` 重绑重跑。
