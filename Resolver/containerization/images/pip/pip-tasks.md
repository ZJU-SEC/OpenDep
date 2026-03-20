# pip 重构任务清单

本文件用于追踪 `Resolver/containerization/images/pip/` 下 pip 依赖解析后端重构的进度。

任务划分基于 [pip-refactoring.md](/Users/xingyu/project/Paper/OpenDep/Resolver/containerization/images/pip/pip-refactoring.md)，并严格遵守当前范围边界：

- 只重构依赖解析能力
- 不包含路径冲突检测
- 不包含 `InstSimulator` 迁移
- 不包含 `detect_MC.py` 迁移
- 不包含 `module_path` 相关能力

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

- 已完成：15 / 15
- 当前已完成任务：`PIP-T00`, `PIP-T01`, `PIP-T02`, `PIP-T03`, `PIP-T04`, `PIP-T05`, `PIP-T06`, `PIP-T07`, `PIP-T08`, `PIP-T09`, `PIP-T10`, `PIP-T11`, `PIP-T12`, `PIP-T13`, `PIP-T14`

## 任务总表

| ID | 状态 | 任务 | 依赖 | 主要产出 | 完成标准 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| PIP-T00 | done | 建立本任务追踪文件 | 无 | `pip-tasks.md` | 已创建任务清单，后续可持续更新状态 | 完成于 2026-03-18 |
| PIP-T01 | done | 搭建 pip backend 目录骨架与入口文件 | 无 | `backend/` 目录、`cli.py` 初始入口、基础模块分层 | 仓库中存在可运行的 backend 骨架，目录职责清晰，未引入真实解析逻辑也能完成最小导入与启动 | 完成于 2026-03-18 |
| PIP-T02 | done | 定义核心数据模型与抽象接口 | PIP-T01 | `PackageMetadataRecord`、`VersionRecord`、`MetadataSource`、`IndexStore` 等接口 | 核心模型和接口已固定，resolver core 不再依赖具体数据库实现细节 | 完成于 2026-03-18 |
| PIP-T03 | done | 抽离 resolver core 与 resolvelib provider | PIP-T01, PIP-T02 | 独立的 resolver core 模块 | 求解逻辑从老 `EnvResolver` 中抽离出来，provider 只依赖抽象接口，不直接写 SQL | 完成于 2026-03-18 |
| PIP-T04 | done | 实现解析结果到统一 graph 的转换层 | PIP-T03 | graph builder / normalizer | 能把解析结果稳定输出为 `root / nodes / edges / semantics / metrics` 结构 | 完成于 2026-03-18 |
| PIP-T05 | done | 实现 archive 读取与发行包选择公共层 | PIP-T01, PIP-T02 | archive reader、artifact selector | 能统一处理 wheel / sdist 的读取与选择策略，并为依赖提取提供稳定输入 | 完成于 2026-03-18 |
| PIP-T06 | done | 实现 wheel 依赖提取器 | PIP-T05 | wheel dependency extractor | 能从 wheel 元数据中提取 `requires_dist`、`requires_python`、`yanked` 所需信息并生成统一记录 | 完成于 2026-03-18 |
| PIP-T07 | done | 实现 sdist 依赖提取器 | PIP-T05 | sdist dependency extractor | 能处理 `setup.py`、`setup.cfg`、`pyproject.toml` 三类主要路径，并生成统一记录 | 完成于 2026-03-18 |
| PIP-T08 | done | 实现 `IndexedMetadataSource` 与 `PostgresIndexStore` | PIP-T02, PIP-T03 | indexed source、Postgres store | 解析可通过抽象 store 读取已有索引数据，resolver core 仍不感知 PostgreSQL 细节 | 完成于 2026-03-18 |
| PIP-T09 | done | 实现 `LiveMetadataSource` 与本地缓存 | PIP-T02, PIP-T03, PIP-T05, PIP-T06, PIP-T07 | live source、本地缓存策略 | 无数据库时可完成候选版本查询与依赖提取，并支持缓存减少重复下载 | 完成于 2026-03-18 |
| PIP-T10 | done | 实现 indexer 写入链路 | PIP-T02, PIP-T05, PIP-T06, PIP-T07, PIP-T08 | indexer CLI / 写库逻辑 | 能离线提取 dependency metadata 并写入 indexed store，为 `indexed` 模式提供数据来源 | 完成于 2026-03-18 |
| PIP-T11 | done | 实现 pip backend CLI 解析主流程 | PIP-T03, PIP-T04, PIP-T08, PIP-T09 | 可执行的 backend CLI | 能根据配置切换 `live` / `indexed` 模式并输出统一 JSON 结果 | 完成于 2026-03-18 |
| PIP-T12 | done | 实现 `runtime/pip_adapter.py` | PIP-T11 | pip adapter | adapter 支持 `health`、`capabilities`、`resolve`，并完成错误映射、超时控制、raw 保留 | 完成于 2026-03-18 |
| PIP-T13 | done | 更新容器接入配置 | PIP-T12 | `Dockerfile`、`docker-compose.yml`、必要配置项 | `resolver-pip` 不再是 placeholder，容器链路可调用真实 backend | 完成于 2026-03-18 |
| PIP-T14 | done | 补齐测试、样例与使用文档 | PIP-T04, PIP-T10, PIP-T11, PIP-T12, PIP-T13 | 单元测试、集成样例、README/说明文档 | 至少覆盖 resolver core、metadata source、adapter 主路径，以及 `live` / `indexed` 的基本使用说明 | 完成于 2026-03-18 |

## 推荐执行顺序

1. `PIP-T01` -> `PIP-T02` -> `PIP-T03`
2. `PIP-T05` -> `PIP-T06` 与 `PIP-T07`
3. `PIP-T08` 与 `PIP-T09`
4. `PIP-T04` -> `PIP-T11` -> `PIP-T12`
5. `PIP-T13` -> `PIP-T14`

## 可并行任务

- `PIP-T04` 可以在 `PIP-T03` 后与部分 source 实现并行推进
- `PIP-T06` 与 `PIP-T07` 可以并行
- `PIP-T08` 与 `PIP-T09` 在接口稳定后可以并行

## 里程碑建议

### 里程碑 A：先跑通 indexed 主链

包含：

- `PIP-T01`
- `PIP-T02`
- `PIP-T03`
- `PIP-T04`
- `PIP-T05`
- `PIP-T06`
- `PIP-T07`
- `PIP-T08`
- `PIP-T11`
- `PIP-T12`
- `PIP-T13`

目标：

- 先复用索引路径，把数据库从“硬编码依赖”改成“可插拔 store”

### 里程碑 B：补齐 live 模式

包含：

- `PIP-T09`

目标：

- 不依赖数据库也能完成解析

### 里程碑 C：补齐预处理与交付质量

包含：

- `PIP-T10`
- `PIP-T14`

目标：

- 提供完整的预提取能力与可维护交付面
