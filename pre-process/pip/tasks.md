# pip 预处理重构任务清单

本文件用于追踪 `pre-process/pip/` 下 pip 数据预处理与建库链路的重构进度。

这份计划不再只基于抽象设计，而是明确参考了两套现有实现：

- 旧版离线依赖提取逻辑：
  - `pre-process/pip/.legacy/dependency-extractor/`
- 已落地的 pip resolver / indexed 读取侧逻辑：
  - `resolving/containerization/images/pip/backend/`
  - `resolving/containerization/images/pip/pip-refactoring.md`
  - `resolving/containerization/images/pip/pip-tasks.md`

因此，本文件关注的核心目标是把“pip 依赖信息预处理”从运行时解析链路中单独抽离出来，并让它成为 `indexed` 模式的正式前序步骤。

## 范围边界

本次只做：

- pip 生态的依赖信息预处理任务拆分
- 与 `pre-process/` 当前目录结构对齐的任务规划
- 以 `indexed` 模式为目标的建库、增量更新、回填与质量校验路径
- 兼容当前 resolver `indexed` 模式的数据库输出
- 迁移或复用 legacy extractor 中仍然有价值的离线提取能力

本次不做：

- `live` 解析模式本身的运行时重构
- `resolvelib` 求解逻辑迁移
- 路径冲突检测
- `InstSimulator` 迁移
- `detect_MC.py` 迁移
- `module_path` 相关索引设计

## 当前代码观察

### 1. legacy dependency-extractor 提供了什么

`pre-process/pip/.legacy/dependency-extractor/` 当前主要提供这些能力：

- 接收“本地包文件路径”作为输入
- 处理 `.whl`、`.egg`、`.tar.gz`、`.zip` 等归档
- 通过 `pkginfo`、`requires.txt`、`setup.py` AST、`setup.cfg`、`pyproject.toml` 提取依赖
- 使用 `peewee` 和 `ProjectsMetadata` 直接绑定 PostgreSQL

其中有价值的部分主要是：

- 老的本地 artifact 输入路径
- `setup.py` AST 依赖追踪思路
- 对 `requires.txt` / `egg-info` 一类旧格式的兼容经验

但也有几个明显问题：

- 提取逻辑、数据库写入、入口命令混在一起
- 代码里保留了很多直接写库和硬编码连接方式
- 一些接口约定不稳定，更适合作为“行为参考”，不适合作为新系统骨架

### 2. resolving 侧已经提供了什么

`resolving/containerization/images/pip/backend/` 当前已经有一套更清晰的实现：

- `inspectors/wheel.py`
- `inspectors/sdist.py`
- `inspectors/setup_parsing.py`
- `indexer/service.py`
- `stores/postgres.py`

这些实现的优点是：

- 已经把 wheel / sdist / setup 文件解析职责拆开
- 已经有统一的 `PackageMetadataRecord`
- 已经有 `PostgresIndexStore`，且当前 `indexed` 模式正在消费它输出的表结构

因此，`pre-process/pip/` 不应该简单复制 legacy 代码，而应该：

1. 以 `resolving` 当前 inspector / store 模型为主线。
2. 把 legacy extractor 作为迁移样本和回归参考。
3. 只把 `resolving` 尚未覆盖、但 legacy 确实支持的离线路径补进来。

## 设计原则

1. `pre-process/` 只负责“数据准备”，`resolving/` 只负责“解析请求”。
2. 首期以兼容当前 `PostgresIndexStore` 为目标，优先产出 resolver 立刻可用的数据库内容。
3. `resolving/containerization/images/pip/backend/inspectors/` 应视为首要复用对象，不在 `pre-process/` 里复制出第三套解析逻辑。
4. `pre-process/pip/.legacy/dependency-extractor/` 应视为迁移参考和行为回归样本，而不是新架构的直接基础。
5. 预处理链路必须支持批量执行、断点续跑、失败重试与增量补洞。
6. 当未来需要升级到新的结构化 schema 时，应通过 loader 层演进，而不是重新改 resolver core。

## 目录映射

按照当前 `pre-process/` 的组织方式，pip 预处理重构建议映射为：

- `pre-process/common/database/`
  - 数据库连接、事务、批量写入、schema 初始化
- `pre-process/common/models/`
  - 跨任务共享的数据记录、作业状态、批处理结果模型
- `pre-process/common/utils/`
  - 日志、重试、序列化、缓存路径、时间与哈希工具
- `pre-process/pip/adapters/`
  - 适配 legacy 本地包路径、包清单输入、PyPI / mirror 输入、resolver inspector bridge
- `pre-process/pip/pipeline/`
  - 版本枚举、artifact 获取、依赖提取、规范化、校验
- `pre-process/pip/loaders/`
  - PostgreSQL schema 初始化、upsert、增量导入、回填入口

## 状态规则

- `todo`: 未开始
- `doing`: 进行中
- `done`: 已完成并已合入当前实现
- `blocked`: 有外部阻塞，暂时无法继续

## 更新规则

- 每完成一个 task，就把对应任务的 `状态` 更新为 `done`。
- 如果任务开始但尚未完成，把 `状态` 更新为 `doing`。
- 如果任务被外部依赖阻塞，把 `状态` 更新为 `blocked`，并在 `备注` 中写明原因。
- 除非任务范围发生变化，否则不要随意改动 task 的 `完成标准`。

## 当前进度

- 已完成：17 / 17
- 当前已完成任务：`PP-PIP-T00`, `PP-PIP-T01`, `PP-PIP-T02`, `PP-PIP-T03`, `PP-PIP-T04`, `PP-PIP-T05`, `PP-PIP-T06`, `PP-PIP-T07`, `PP-PIP-T08`, `PP-PIP-T09`, `PP-PIP-T10`, `PP-PIP-T11`, `PP-PIP-T12`, `PP-PIP-T13`, `PP-PIP-T14`, `PP-PIP-T15`, `PP-PIP-T16`
- 当前进行中任务：无

## 任务总表

| ID | 状态 | 任务 | 依赖 | 主要目录 | 主要产出 | 完成标准 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PP-PIP-T00 | done | 建立本任务追踪文件 | 无 | `pre-process/pip/` | `tasks.md` | 已创建任务清单，后续可持续更新状态 | 完成于 2026-03-18 |
| PP-PIP-T01 | done | 梳理 legacy extractor 与 resolving inspector 的能力映射 | PP-PIP-T00 | `pre-process/pip/` | 能力对照、迁移清单、缺口列表 | 明确 legacy 中哪些能力保留、哪些废弃、哪些由 `resolving/.../inspectors/` 直接复用 | 完成于 2026-03-18；能力映射结论已收敛到当前代码结构、测试和 README 中的受支持工作流说明 |
| PP-PIP-T02 | done | 明确 pre-process、resolving 与共享提取层的边界 | PP-PIP-T01 | `pre-process/pip/`, `resolving/containerization/images/pip/` | 职责边界说明、共享策略、首期接口契约 | 明确哪些逻辑留在 resolver 运行时，哪些进入 pre-process，以及首期是否桥接或抽 shared 模块 | 完成于 2026-03-18；边界约定已体现在当前 bridge / loader / indexed table 契约和 README 中 |
| PP-PIP-T03 | done | 定义 pip 预处理内部数据模型与作业模型 | PP-PIP-T02 | `pre-process/common/models/`, `pre-process/pip/pipeline/` | 原始输入记录、artifact 记录、规范化 metadata record、批处理结果、失败记录模型 | 预处理各阶段之间不再传裸字典，能够稳定表达 package/version/artifact/dependency/extraction result | 完成于 2026-03-18；已把 extraction / validation / batch / failure dataclass 收敛到 `pre-process/common/models/`，`pip_models.py` 保留兼容出口 |
| PP-PIP-T04 | done | 搭建通用数据库、日志、重试与配置基础设施 | PP-PIP-T02 | `pre-process/common/database/`, `pre-process/common/utils/` | DSN 配置、连接工厂、事务辅助、日志与重试工具 | pip 预处理任务不再各自拼接数据库连接和基础控制逻辑 | 完成于 2026-03-18；已补共享 PostgreSQL 事务辅助、日志工具、重试工具，并接入 loader / batch runner / load CLI |
| PP-PIP-T05 | done | 实现 legacy 本地 artifact 输入适配层 | PP-PIP-T01, PP-PIP-T03 | `pre-process/pip/adapters/` | local artifact adapter、archive 输入契约 | 能从本地 `.whl`、`.egg`、`.tar.gz`、`.zip` 路径生成统一 extraction job | 完成于 2026-03-18 |
| PP-PIP-T06 | done | 实现 resolver inspector bridge / 共享提取 facade | PP-PIP-T01, PP-PIP-T02, PP-PIP-T03 | `pre-process/pip/adapters/`, `pre-process/pip/pipeline/` | 对 `wheel.py`、`sdist.py`、`setup_parsing.py` 的桥接层 | 预处理主链优先复用 `resolving` 当前 inspector 能力，并为缺失能力预留补充扩展点 | 完成于 2026-03-18 |
| PP-PIP-T07 | done | 实现包清单、显式版本与批量任务输入适配层 | PP-PIP-T03, PP-PIP-T04 | `pre-process/pip/adapters/` | manifest adapter、batch input adapter、显式版本适配器 | 能从单包、指定版本列表、批量清单三类输入生成统一作业对象 | 完成于 2026-03-18；已支持 `--project name`、`--project name==version`、artifact + package manifest、top-level defaults 与相对路径解析 |
| PP-PIP-T08 | done | 实现版本枚举与任务规划阶段 | PP-PIP-T06, PP-PIP-T07 | `pre-process/pip/pipeline/` | 版本选择器、yanked 过滤、latest-N 规划逻辑 | 能根据项目名、显式版本、limit、include-yanked 等参数生成稳定的版本处理计划 | 完成于 2026-03-18；已补 `PyPIJsonClient` 与 `VersionPlanner`，版本选择行为对齐当前 backend `index_project` 规则 |
| PP-PIP-T09 | done | 实现 artifact 获取、mirror 读取、缓存与重试阶段 | PP-PIP-T04, PP-PIP-T05, PP-PIP-T08 | `pre-process/pip/pipeline/` | 下载器、mirror reader、缓存目录约定、失败重试策略 | 同一个版本不会被重复下载，支持本地 mirror / 本地文件 / 远端抓取三类输入 | 完成于 2026-03-18；已支持 release JSON 缓存、artifact 缓存、本地 mirror 优先命中、远端下载回退与 artifact URL/hash 透传 |
| PP-PIP-T10 | done | 实现单发行包依赖提取与规范化主流程 | PP-PIP-T05, PP-PIP-T06, PP-PIP-T09 | `pre-process/pip/pipeline/` | extraction pipeline、规范化记录、source-kind 对齐 | 能将 wheel/sdist 提取结果统一转换为规范化 metadata record，包含 `requires_dist`、`requires_python`、`yanked`、`source_kind` 等字段 | 完成于 2026-03-18 |
| PP-PIP-T11 | done | 补齐 legacy 特有格式与边角行为兼容 | PP-PIP-T01, PP-PIP-T06, PP-PIP-T10 | `pre-process/pip/pipeline/` | `requires.txt`、旧式 `egg-info`、特殊 `setup.py` 行为兼容清单 | 在不污染主流程的前提下，保留 legacy extractor 中仍然必要的离线提取能力 | 完成于 2026-03-18；已补 `EGG-INFO/requires.txt`、section marker 解析、`PKG-INFO/METADATA`、`setup.cfg`、`pyproject.toml`、`setup.py`、`requirements*.txt` fallback，并增加回归测试 |
| PP-PIP-T12 | done | 实现质量校验、warning 规范化与失败归档 | PP-PIP-T03, PP-PIP-T10, PP-PIP-T11 | `pre-process/pip/pipeline/`, `pre-process/common/utils/` | record validator、warning/error report、failure sink | 能区分成功、部分成功、失败、可重试失败，并把 warning 与失败原因稳定落盘或输出 | 完成于 2026-03-18 |
| PP-PIP-T13 | done | 实现 PostgreSQL schema 初始化与兼容 loader | PP-PIP-T03, PP-PIP-T04, PP-PIP-T10 | `pre-process/pip/loaders/`, `pre-process/common/database/` | schema init、Postgres upsert loader | 能一键初始化当前 indexed 模式所需表结构，并把记录写成 resolver 当前可消费的数据格式 | 完成于 2026-03-18 |
| PP-PIP-T14 | done | 实现批量建库 CLI / job runner | PP-PIP-T07, PP-PIP-T08, PP-PIP-T10, PP-PIP-T13 | `pre-process/pip/`, `pre-process/pip/loaders/` | CLI 入口、单包/批量执行器、结构化 summary | 可以从命令行触发单包、单批次、清单式建库任务，并输出结构化结果 | 完成于 2026-03-18；当前已覆盖本地 artifact、多 artifact、manifest 驱动批处理，远端版本规划继续由 `PP-PIP-T07` ~ `PP-PIP-T09` 扩展 |
| PP-PIP-T15 | done | 实现增量更新、跳过已存在、断点续跑与补洞 | PP-PIP-T12, PP-PIP-T13, PP-PIP-T14 | `pre-process/pip/loaders/`, `pre-process/pip/pipeline/` | skip-existing、resume、backfill 策略 | 长任务中断后可恢复，已成功版本不会重复处理，补洞任务可独立执行 | 完成于 2026-03-18；已补 `loader.has_release/list_versions`、`--skip-existing`、`--backfill`、`--state-file`、JSONL state tracker 与对应回归测试 |
| PP-PIP-T16 | done | 接入 resolver indexed 模式联调、补齐测试与文档 | PP-PIP-T13, PP-PIP-T14, PP-PIP-T15 | `pre-process/pip/`, `resolving/containerization/images/pip/`, `pre-process/common/` | 联调说明、兼容性验证、测试、样例、README | 用 pre-process 建出的数据库可以被当前 pip resolver 的 `indexed` 模式直接消费，并有最小可复现文档 | 完成于 2026-03-18；已补 preprocess -> resolver 的最小联调文档，并增加基于 `PostgresIndexStore` / `IndexedMetadataSource` 的兼容性测试 |

## 推荐执行顺序

1. `PP-PIP-T01` -> `PP-PIP-T02`
2. `PP-PIP-T03` -> `PP-PIP-T04`
3. `PP-PIP-T05` -> `PP-PIP-T06`
4. `PP-PIP-T07` -> `PP-PIP-T08` -> `PP-PIP-T09`
5. `PP-PIP-T10` -> `PP-PIP-T11` -> `PP-PIP-T12`
6. `PP-PIP-T13` -> `PP-PIP-T14` -> `PP-PIP-T15`
7. `PP-PIP-T16`

## 可并行任务

- `PP-PIP-T03` 与 `PP-PIP-T04` 的后半段可以并行推进
- `PP-PIP-T05` 与 `PP-PIP-T07` 可以在模型稳定后并行
- `PP-PIP-T12` 可以在 `PP-PIP-T10` 基本稳定后与 `PP-PIP-T13` 并行

## 里程碑建议

### 里程碑 A：先跑通单 artifact 到单条入库主链

包含：

- `PP-PIP-T01`
- `PP-PIP-T02`
- `PP-PIP-T03`
- `PP-PIP-T04`
- `PP-PIP-T05`
- `PP-PIP-T06`
- `PP-PIP-T10`
- `PP-PIP-T13`

目标：

- 从一个本地或已下载的发行包出发，完成依赖提取、规范化和兼容写库

### 里程碑 B：补齐批量任务与离线数据源

包含：

- `PP-PIP-T07`
- `PP-PIP-T08`
- `PP-PIP-T09`
- `PP-PIP-T14`

目标：

- 支持从包清单、版本范围、PyPI mirror 和远端索引出发批量构建 indexed 数据库

### 里程碑 C：补齐兼容性、恢复能力与交付面

包含：

- `PP-PIP-T11`
- `PP-PIP-T12`
- `PP-PIP-T15`
- `PP-PIP-T16`

目标：

- 让 `pre-process/pip/` 成为独立、可交付、可复用的 pip 建库入口，并与当前 resolver indexed 模式稳定对接

## 首期落地建议

为了降低迁移风险，建议第一阶段优先遵循下面四条：

1. 数据库 loader 先兼容当前 `resolving/containerization/images/pip/backend/stores/postgres.py` 正在消费的列结构，但落到共享数据库中的 pip 专属表 `pip_projects_metadata`，而不是继续使用通用的 `projects_metadata` 表名。
2. 依赖提取逻辑先桥接 `resolving/containerization/images/pip/backend/inspectors/`，不要在 `pre-process/` 中直接复制一套新的 wheel/sdist/setup 解析代码。
3. `pre-process/pip/.legacy/dependency-extractor/` 主要作为行为样本、fixture 来源和兼容性参考，不直接沿用其中的 `peewee` 写库模型与入口脚本结构。
4. 首期先把“单 artifact 输入 -> 规范化记录 -> PostgreSQL 入库”这条最小闭环跑通，再扩展到批量版本规划和断点续跑。
