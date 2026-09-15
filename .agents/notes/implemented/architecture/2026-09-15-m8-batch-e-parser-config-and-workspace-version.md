# Agent Note: M8 批次 E parser 配置入口与旧 workspace 版本策略

Status: implemented

[中文](./2026-09-15-m8-batch-e-parser-config-and-workspace-version.md) | [English](./2026-09-15-m8-batch-e-parser-config-and-workspace-version.en.md)

## 问题

[`docs/development/m8.md`](../../../../docs/development/m8.md) §E 要求「旧 workspace 可读、可迁移或明确拒绝，禁止静默破坏」以及「切换 parser 必须改配置并失效批次 C 的下游缓存」，但批次 A–D 都把这两条边界显式推迟：`workspace.py` 只写「migration belongs to M8 batch E」，[`storage.md`](../../../../docs/architecture/storage.md) 两处写「迁移属批次 E」。落地时缺两样东西。

第一，版本判定只有一条不等号：`version != WORKSPACE_VERSION` 抛 `WorkspaceVersionError`，消息只说「expected '0.1.0'」——没有「这是哪个文件、本构建能读什么、我该怎么办」，也没有具名的可读集合。Bump `WORKSPACE_VERSION` 时不会有任何东西迫使作者面对「旧版本还读不读」这个问题。

第二，也是更硬的缺口：**没有任何 registry 覆盖入口**。`capabilities._registry_text()` 直接读 package data，`run_pipeline`、CLI 与 `apps/` 全都没有 registry 参数或环境变量，要换 parser 只能改源码里的 `data/capability-registry.toml` 再重启。而 `registry_fingerprint()` 永远哈希内置字节，因此即使加了入口，只要指纹不跟随**实际使用的** registry，§E 的「切换 parser 失效下游缓存」就永远不成立——覆盖生效而缓存键不变，是静默陈旧。

真实 MinerU / Docling / GROBID 输出本轮仍不可得，因此本批只做配置入口与具名拒绝策略，真实工具验证继续标为缺口（`provenance.json` 全是 `synthetic-contract`，内置 primary 仍是 `mock` / `docling-sim` / `grobid-sim`）。

## 决策

1. **「可读 / 可迁移 / 拒绝」落地为具名可读集合加明确拒绝。** `workspace.py` 新增 `SUPPORTED_WORKSPACE_VERSIONS: tuple[str, ...] = ("0.1.0",)`——写成显式字面量而不是从 `WORKSPACE_VERSION` 派生，派生写法会在 bump 时静默遗忘旧版本。`_load_existing` 在 `version` 不是字符串或不在集合内时抛 `WorkspaceVersionError`，消息含清单路径、写入版本、本构建可读版本与「换目录或删掉 workspace 重建」的指引。`raise` 仍在任何 `self.*` 赋值之前，因此被拒绝的 workspace 在磁盘与内存里都不被触碰。
2. **本批不写版本转换函数。** 批次 A–D 写的都是 `"0.1.0"`，清单形状从未变过：批次 C 改的是键材料（配置折进 `inputFingerprint`），批次 D 加的是 status 取值（`StageStatus.DEGRADED`），两者都不改清单字段。旧 workspace 因此**本来就仍然可读**，且因键失配自然重跑——没有旧格式可迁，写转换器只会是死代码。未来 bump 时二选一：把旧版本加进集合并在 `_load_existing` 里加真实迁移步骤，或保持拒绝。
3. **parser 配置只有一个入口**：新增 `pdf_pipeline/config.py`，`ParserConfig`（frozen dataclass，字段 `registry_path: Path | None`）加 `load_parser_config()`，刻意镜像 `paper_llm.config` 的 `TranslationConfig` + `load_translation_config` 形状，不引入第二套 env→dataclass 约定。环境变量名 `PAPER_CAPABILITY_REGISTRY`（`REGISTRY_PATH_ENV`），与代码与文档里既有的 `Capability Registry` / `capability-registry.toml` 同名一处。
4. **优先级固定为 flag > env > 内置。** CLI 新增 `--registry <file>`，`main` 里 `ParserConfig(registry_path=args.registry) if args.registry else None`，未给 flag 时传 `None`，由 `run_pipeline` 读 env；env 未设时 `registry_path` 为 `None`，用内置 registry。
5. **`capabilities` 全面参数化，覆盖不缓存。** `load_registry(path=None)`：`None` → `_bundled_registry()`（`lru_cache(maxsize=1)` 包 `_parse_registry(_registry_text(), source="bundled capability-registry.toml")`，package data 进程内不可变故可缓存）；给定路径 → 每次实读实解析。新公开 `registry_text(path=None)` 返回原始 TOML。`_load_registry_impl` 重命名为 `_parse_registry(text, *, source)`，`_validate(registry, *, source)` 一并接收来源。
6. **覆盖文件的内容入键，路径不入键。** `registry_fingerprint(path=None)` 改为 `sha256(registry_text(path))`：覆盖时指纹跟随覆盖文件内容，这正是 §E 验收条款的实现点；同一份内容写到两个不同路径得到同一摘要，内容与内置逐字节相同的副本不引发任何重跑。
7. **单次读取的 `resolve_registry(path=None) -> tuple[Registry, str]`。** 一次运行必须用它路由的 registry 与它写进阶段键的摘要完全一致：读两次会让两次读之间的编辑记录下一个与产物不符的摘要，形成静默缓存命中。`path is None` 时返回缓存的内置表与内置摘要；否则一次 `registry_text` 读出文本，再由同一次文本派生表与摘要。
8. **坏配置一律拒绝，绝不回退内置。** 新增 `CapabilityRegistryError(ValueError)`（继承 `ValueError`，既有 `pytest.raises(ValueError)` 不受影响），覆盖读取失败（`OSError` / `UnicodeError`）、TOML 解析失败、以及全部 `_validate` 不变量违反（缺 internal capability、internal capability 被非 `internal` 占据、某 capability 重复列 provider）；消息都带来源（路径或 `bundled …`）。静默回退到内置 registry 等于静默换了 parser，是本批最不能接受的行为。
9. **`run_pipeline` 在构造 workspace 之前解析一次 registry 并向下传。** 新增关键字参数 `pipeline_config: ParserConfig | None = None`；`registry, registry_digest = resolve_registry(parser_config.registry_path)` 放在 `WorkspaceManager(...)` **之前**——坏 registry 必须在碰任何磁盘状态之前就失败。`stage_config_inputs(config, source_bytes, *, registry_digest=None)` 用 `registry_digest or registry_fingerprint()`；`_run_evidence_stage` / `_run_layout_stage` 增 keyword-only `registry: Registry` 参数（沿用同文件 `_run_semantic_stage` 的既有风格），`_ensure_analysis_stages` 透传，两个 runner 不再各自 `load_registry()`。文档化不变量：用覆盖 registry 路由的调用方**必须**把该 registry 的摘要传给 `stage_config_inputs`。
10. **`rerender_workspace` 不加该参数。** 它只重写 TRANSLATE/RENDER 的 `make_stage_record`，而这两个阶段由 `stage_config_inputs` 得到的配置是 `common + {targetLocale, sourceLocale, providerModel, providerEndpoint, terminologyFile}` 与 `{renderProfile, renderPolicy, latexTemplate}`，**不含 `capabilityRegistry`**；EVIDENCE/LAYOUT 记录它完全不碰。因此 registry 覆盖不影响它的缓存键正确性，加参数只会是无观测差异的管线。
11. **内置 registry 不动。** `data/capability-registry.toml` 未改，primary 仍是 `mock` / `docling-sim` / `grobid-sim`。改内置 primary 属「有意替换」：先用覆盖文件跑 `just benchmark` 证明，再单独提交。
12. **benchmark 走同一个入口。** `tests/benchmark/run_benchmark.py` 的 `load_registry()` 改为 `load_registry(load_parser_config().registry_path)`，于是「用覆盖 registry 跑 benchmark 证明升级」是一条命令（`PAPER_CAPABILITY_REGISTRY=<file> just benchmark`），CI 无 env 时行为与今天逐字节一致。
13. **`apps/api` / `apps/worker` 不加 registry 参数。** 两者都是纯 argv 接线且不读 env；`run_pipeline` / `rerender_workspace` 的默认值在进程内读 env，所以给 worker 进程设 `PAPER_CAPABILITY_REGISTRY` 即对两条路径同时生效，无需改任何 app，也不引入 `JobRecord` 字段。
14. **文档分工。** 操作说明进 `packages/python/pdf-pipeline/README.md`（怎么设、优先级、默认不变、改内置 primary 前先 benchmark）；缓存键与拒绝语义的当前态进 [`docs/architecture/storage.md`](../../../../docs/architecture/storage.md)；`run_pipeline` 的行为进 [`docs/architecture/pipeline.md`](../../../../docs/architecture/pipeline.md)；分级与验收进 [`docs/development/m8.md`](../../../../docs/development/m8.md)。一事一处，不复制。

## 考虑过的替代方案

- **写 `migrate_workspace()` 把旧版本转成新版本**：没有任何旧值可转（批次 A–D 的 `workspaceVersion` 都是 `"0.1.0"`，清单形状没变），函数体只能是「原样返回」。真 bump 时再写、并为它写测试，才是让迁移路径被真实覆盖的做法。
- **`SUPPORTED_WORKSPACE_VERSIONS = (WORKSPACE_VERSION,)`**：bump `WORKSPACE_VERSION` 时会静默把旧版本踢出可读集合，且代码里看不出「旧版本还读不读」是个决定。显式字面量迫使提版本的人面对这个问题。
- **bump `WORKSPACE_VERSION` 以标记本批**：本批不改清单形状（只加了一个代码侧可读集合与一个配置入口），bump 只会无理由拒绝所有既有 workspace。批次 C 已确立的规则是「键材料扩展只让旧 workspace 重跑一次，是安全方向」。
- **覆盖 registry 时回退到内置（读失败就当作没覆盖）**：静默回退等于静默换了 parser，正是本批要消灭的失败模式。
- **缓存覆盖文件的解析结果**：操作者可以在两次运行之间编辑它，缓存会把「改了配置」变成「没改」。只有内置 package data 值得缓存。
- **`registry_fingerprint(path)` 里 `path.read_text()` 与 `registry_text(path)` 各读一次**：两次读之间的编辑会让记录的摘要与用它产出的产物不符，是静默缓存命中；`resolve_registry` 的存在就是为了让一次运行只读一次。
- **指纹里加路径**（如 `sha256(path + content)`）：路径不是语义输入；同内容的两个路径会得到两个键，把一个无意义的「换了个文件名」变成两个阶段重跑。
- **把 `--registry` 同时加到 `apps/worker`**：app 层不为这件事承担参数；env 已覆盖两条路径，加参数会引入需要同步的第二处配置面（以及潜在 `JobRecord` 字段）。
- **`CapabilityRegistryError` 不继承 `ValueError`**：会让既有 `pytest.raises(ValueError)` 与任何按 `ValueError` 捕获 registry 问题的调用方漏掉；继承是零成本的兼容。
- **把 `registry` 参数做成位置参数传给两个 runner**：同文件 `_run_semantic_stage` 已确立 keyword-only 风格，位置参数还会遮蔽未来新增参数的位置含义。
- **在 registry 覆盖变化时也重跑 TRANSLATE/RENDER**：那两个阶段不消费 registry，多跑只会掩盖「键是否正确」的观察。

## 后果

- 新增 `packages/python/pdf-pipeline/src/pdf_pipeline/config.py`：`REGISTRY_PATH_ENV`、`ParserConfig`、`load_parser_config`。
- `pdf_pipeline/capabilities.py`：新增 `CapabilityRegistryError`、`registry_text(path=None)`、`resolve_registry(path=None)`、`_bundled_registry()`；`load_registry` / `registry_fingerprint` 增可选 `path`；`_load_registry_impl` → `_parse_registry(text, *, source)`；`_validate(registry, *, source)`；新增 `pathlib.Path` 导入。
- `pdf_pipeline/pipeline.py`：`stage_config_inputs(..., *, registry_digest=None)`；`_run_evidence_stage` / `_run_layout_stage` 增 keyword-only `registry`；`_ensure_analysis_stages(..., *, registry)`；`run_pipeline(..., pipeline_config=None)` 在构造 workspace 前 `resolve_registry`；CLI 增 `--registry`；import 行改为 `registry_fingerprint, resolve_registry`（`load_registry` 不再被本模块引用）。
- `pdf_pipeline/workspace.py`：新增 `SUPPORTED_WORKSPACE_VERSIONS`；`_load_existing` 的版本判定改为具名集合 + 带指引的消息；模块 docstring 的「migration belongs to M8 batch E」改为当前事实。
- `tests/benchmark/run_benchmark.py`：registry 取自 `load_parser_config()`。
- 测试：新增 `tests/test_parser_config.py` 10 项（默认/读取 env、覆盖生效且指纹跟随、内容而非路径入键、编辑后指纹变化、缺失/非法/缺 internal capability 三类拒绝、`resolve_registry` 单次读取）；`test_workspace.py` 把 `test_unknown_workspace_version_rejected` 换成 `test_supported_workspace_version_loads`、`test_unknown_workspace_version_refused_without_touching`（清单字节不变 + 无 `.staging`）与 `test_manifest_absent_directory_is_not_trusted`；`test_pipeline_resume.py` 的 `test_registry_change_reruns_evidence_and_layout`（原本 monkeypatch `pipeline.registry_fingerprint`，改造后不再被读取）替换为三个走真实配置入口的测试：覆盖变化 → EVIDENCE/LAYOUT 各跑 1 次且 `probe.json` 的 `routing[0].provider == "mineru"`、`degradations[0].provider == "mineru"`、`workspace.json` 的 `evidence.status == "degraded"`（E 与 D 的接口连通）；内容相同的副本 → 全 runner 0 次；`--registry` flag → 路由跟随覆盖。`test_specialist_isolation.py` 的三项从 monkeypatch `pipeline.load_registry` 迁移到真实覆盖文件（`_registry_override` 把 overlay 写成 TOML），因此批次 D 的隔离路径现在也由真实配置入口驱动。
- 调用点已全部迁移：`pipeline`、`run_benchmark`、`test_fake_specialists` / `test_fusion` / `test_routing` / `test_semantic`（只用默认 `load_registry()`，签名兼容）；无兼容垫片，无弃用路径。
- 既有 workspace 不受影响：未给 flag、未设 env 时内置 registry 的字节与今天逐字节相同，`registry_fingerprint()` 不变，因此缓存键不变、golden 与 benchmark baseline 不动。
- 观察到的行为：无 env / 无 flag 时 `just test-golden` 与 `just benchmark` 结果与今日一致；`--registry` 指向把 `layout.region.primary` 改为 `mineru` 的覆盖文件时，`probe.json` 的 `routing[0].provider == "mineru"`、`degradations[0].provider == "mineru"`、`workspace.json` 中 EVIDENCE 为 `degraded` 而 `ingest`/`physical` 记录字节不变；`--registry /tmp/nope.toml` 在碰 workspace 之前抛 `CapabilityRegistryError`（消息含路径）且 `workspace.json` 字节不变。
- 仍未验证：真实 MinerU / Docling / GROBID 工具输出；因此本批不把内置 primary 换成真实工具，也不为让测试通过而伪造 dump（`tests/fixtures/parser-dumps/provenance.json` 保持 `synthetic-contract`）。
