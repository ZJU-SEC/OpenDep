# pip 依赖解析后端重构方案

## 1. 背景

本文档最初用于设计从 placeholder 迁移到真实 pip backend 的重构方案。
当前仓库中，新的容器化 pip backend 已经落地在 `resolving/containerization/images/pip/backend/`，老逻辑仍保留在 `resolving/containerization/images/pip/.legacy/ModuleGuard/` 作为参考实现。

老的 `ModuleGuard` 本质上由两部分组成：

- `InstSimulator`
  - 从 wheel / sdist / 本地目录中推导安装后模块路径。
- `EnvResolver`
  - 先提取直接依赖，再用 `resolvelib` 做依赖图解析。
  - 解析候选版本时直接查询 `projects_metadata` 数据库表。

但这次重构的目标不是整体迁移 `ModuleGuard`，而是只抽离其中的“依赖解析”能力，也就是以 `EnvResolver` 为核心的这条主链。

本次明确不在范围内的内容：

- 路径冲突检测
- 模块路径模拟与安装后文件路径推导
- `detect_MC.py`
- `InstSimulator` 作为一个独立能力的迁移
- `module_path` 相关索引与查询

老实现能跑起来，但它把三个本该分离的职责绑在了一起：

1. 依赖提取
2. 依赖解析
3. 元数据存储

这正是当前 `pip` 与 `maven / cargo / go / npm` 最大的不同点，也是重构时最需要拆开的部分。

## 2. 先回答两个核心问题

### 2.1 能否解除数据库绑定

可以，而且我认为应该解除。

但这里的“解除数据库绑定”不是指彻底放弃数据库，而是指：

- `resolver core` 不再直接依赖 PostgreSQL / Peewee / SQL 语句；
- 解析器只依赖一个抽象的 `metadata source` 接口；
- 数据库退化为一种可选的元数据来源或缓存实现；
- 在没有数据库时，也能通过实时拉取包文件并现场提取元数据完成解析。

也就是说，真正要消除的是“架构绑定”，不是“所有数据库能力”。

### 2.2 是否应该提供两种配置

应该，而且这是最适合 `pip` 的方案。

我建议对外提供两个正式模式：

- `live` 模式
  - 不依赖数据库。
  - 解析时实时访问包索引、下载分发包、提取依赖信息。
  - 上手最简单，但最慢。
- `indexed` 模式
  - 依赖预提取得到的索引库。
  - 解析时直接读取预先整理好的元数据。
  - 更快、更稳定，但需要前置构建索引。

这两个模式应该共享同一套提取逻辑和同一套解析核心，只替换“元数据从哪里来”。

## 3. 对老实现的观察

基于当前 `.legacy/ModuleGuard`，我认为老代码的关键问题有这些：

### 3.1 解析核心与存储实现耦合过深

`EnvResolver/pypi_wheel.py` 里的 provider 直接拼 SQL 查询 `projects_metadata`，这意味着：

- 解析算法无法脱离数据库单独测试；
- 无法无缝切换到实时提取模式；
- 存储层一改，解析层就要跟着改。

### 3.2 依赖提取逻辑重复且分散

当前和依赖解析直接相关的提取逻辑主要散落在：

- `EnvResolver/get_dep_information.py`
- `EnvResolver/setup_parse_dep.py`

另外，`InstSimulator` 中也有一套 archive / `setup.py` / `setup.cfg` / `pyproject.toml` 处理思路，可作为参考，但它不是本次迁移目标。

当前的问题在于：与依赖解析主链有关的包文件处理逻辑没有被收敛成一个统一抽象。

### 3.3 老数据库表字段比当前范围真正需要的更多

从现有代码看，真正与解析直接强相关的核心字段主要是：

- `name`
- `version`
- `dependency`
- `yanked`
- `version_struct`

像 `module_path`、路径冲突分析相关字段，不属于本次重构范围，不应该继续进入新的 `resolve` 主路径设计。

### 3.4 数据序列化方式不理想

老代码里有多处 `eval(...)` 读取数据库中存的 Python 字面量字符串，这会带来：

- 安全风险
- 兼容性风险
- 跨语言与跨存储实现困难

新设计里应该统一改成 JSON / JSONB 之类的结构化格式。

## 4. 重构目标

新的 `pip` backend 我建议明确追求下面几个目标：

1. 对齐当前 containerized resolver 架构
   - `runtime/pip_adapter.py` 负责协议桥接
   - `images/pip/` 内部 backend 负责真正解析
2. 让 resolver core 与数据库解耦
3. 复用一套依赖提取逻辑，同时支持 `live` 和 `indexed`
4. 最终直接输出统一 graph JSON
   - `root`
   - `nodes`
   - `edges`
   - `semantics`
   - `metrics`

## 5. 推荐的新架构

我建议把新的 `pip` 后端拆成下面几层：

```text
gateway
  -> docker_gateway_proxy
  -> runtime/pip_adapter.py
  -> pip backend CLI
     -> resolver core
     -> metadata source
        -> live source
        -> indexed source
     -> artifact inspector
        -> dependency extractor
     -> optional indexer / storage adapter
```

### 5.1 模块职责

#### A. `pip_adapter.py`

职责保持和其他生态一致：

- 处理 `health` / `capabilities`
- 调用 pip backend CLI
- 做 timeout / error code / raw 输出映射
- 输出统一 response envelope

#### B. `resolver core`

这是新的解析核心，建议保留 `resolvelib`，但重写 provider 的数据来源。

核心原则：

- 它不应该知道底层是 PostgreSQL、SQLite、文件缓存还是实时联网；
- 它只应该依赖统一接口，例如：
  - `list_versions(name)`
  - `get_release_metadata(name, version)`

#### C. `artifact inspector`

这是从老 `EnvResolver/get_dep_information.py` 以及相关 archive 处理逻辑中提炼出来的统一提取层。

它负责：

- 选择合适的发行包
  - 优先 wheel
  - metadata 足够时避免完整解压
  - wheel 不足时再退回 sdist
- 提取直接依赖

本次重构里，它只服务于 dependency metadata 提取，不承担模块路径模拟职责。

#### D. `metadata source`

这是本次重构最关键的抽象。

建议定义统一接口，例如：

```text
MetadataSource
  - list_versions(project_name) -> list[VersionRecord]
  - get_release(project_name, version) -> PackageMetadataRecord | None
  - warm(project_name, version) -> PackageMetadataRecord
```

其中 `PackageMetadataRecord` 至少包含：

- `name`
- `version`
- `requires_dist`
- `requires_python`
- `yanked`
- `source_kind`
  - `wheel-metadata`
  - `sdist-setup.py`
  - `sdist-setup.cfg`
  - `sdist-pyproject.toml`

### 5.2 两个实现

#### 实现 1: `LiveMetadataSource`

特点：

- 不依赖数据库
- 在解析时实时访问索引和包文件
- 使用本地文件缓存提升重复请求性能

工作流：

1. 查询包的可用版本列表
2. 根据 `resolvelib` 选择候选版本
3. 若本地缓存无元数据，则下载对应 wheel / sdist
4. 调用 `artifact inspector` 提取依赖
5. 把结果返回给 `resolver core`

#### 实现 2: `IndexedMetadataSource`

特点：

- 读取预提取得到的索引库
- 解析更快
- 更适合批量实验、离线环境和大规模调用

工作流：

1. `resolver core` 请求版本列表或版本元数据
2. `IndexedMetadataSource` 直接读索引
3. 返回规范化后的 `PackageMetadataRecord`

这个实现不应再把 PostgreSQL 写死在 resolver 里，而应该进一步拆成：

```text
IndexedMetadataSource
  -> IndexStore
     -> PostgresIndexStore
```

这样后续即使要加 SQLite，也不需要动解析核心。

## 6. 两种模式如何落地

### 6.1 对外只暴露两种正式配置

我建议默认只宣传两种配置：

#### 配置 A: `live`

适合：

- 第一次上手
- 本地开发
- 无数据库环境

建议默认行为：

- `PIP_METADATA_MODE=live`
- 开启本地缓存目录

原因是这次重构只覆盖依赖解析主链，不包含模块路径与冲突检测能力。

建议示例配置：

```text
PIP_METADATA_MODE=live
PIP_CACHE_DIR=/tmp/opendep-pip-cache
PIP_INDEX_FALLBACK_TO_LIVE=false
```

#### 配置 B: `indexed`

适合：

- 已经有预处理流程
- 追求性能与稳定性
- 做批量解析或论文实验

建议默认行为：

- `PIP_METADATA_MODE=indexed`
- 配置索引存储连接
- 由单独的 indexer 负责预填充数据

建议示例配置：

```text
PIP_METADATA_MODE=indexed
PIP_INDEX_BACKEND=postgres
PIP_INDEX_DSN=postgresql://user:password@host:5432/opendep_pip
PIP_INDEX_FALLBACK_TO_LIVE=false
```

### 6.2 内部可以支持“indexed miss 回退 live”

虽然对外只宣传两种模式，但实现上我建议保留一个可选开关：

- `PIP_INDEX_FALLBACK_TO_LIVE=true`

好处是：

- 索引不完整时不会直接失败
- 可以边解析边补洞
- 对调试和冷启动更友好

但它不需要成为第三种公开模式；它更适合当 `indexed` 的增强选项。

## 7. 本次范围边界

为了避免后续实现再次漂移，这里明确记录本次边界：

本次只做：

- 直接依赖提取
- 候选版本查询
- 基于 `resolvelib` 的依赖图解析
- `live` / `indexed` 两种 metadata source 设计
- 与当前 containerized resolver 架构对齐

本次不做：

- 路径冲突检测
- 安装后模块路径推导
- `InstSimulator` 的功能迁移
- `detect_MC` 的功能迁移
- `module_path` 相关数据模型与索引设计

这意味着新的 `resolve` 主路径只依赖 dependency metadata，不依赖模块路径信息。

## 8. 建议的数据模型

我建议新的索引模型使用结构化字段，不再存 Python 字符串。

### 8.1 最小必需字段

- `name_normalized`
- `version`
- `version_sort_key`
- `requires_dist` JSON
- `requires_python`
- `yanked`
- `source_kind`
- `artifact_url`
- `artifact_hash`
- `extracted_at`

### 8.2 可选字段

- `dependency_source_detail`
- `parse_warnings` JSON

### 8.3 兼容性建议

- 保留原始版本字符串
- 同时保存可排序版本键，替代老的 `version_struct`
- 所有列表/字典字段统一存 JSON

本次建议不要把 `module_path` 一类字段纳入新索引模型；如果未来要恢复冲突检测能力，再单独扩展。

## 9. 推荐目录形态

建议在 `resolving/containerization/images/pip/` 下新增真正的 backend 代码，例如：

```text
resolving/containerization/images/pip/
  backend/
    cli.py
    resolver_core/
    metadata_sources/
    inspectors/
    stores/
    indexer/
  pip-refactoring.md
  Dockerfile
```

并在 `resolving/containerization/runtime/` 下新增：

- `pip_adapter.py`

其中职责边界要非常明确：

- `runtime/pip_adapter.py`
  - 只负责协议桥接
- `images/pip/backend/*`
  - 只负责 pip 生态逻辑

## 10. 推荐迁移顺序

虽然最终目标是双模式，但实现顺序不建议一次性大改。

### 阶段 1: 先把“数据库能力”包进接口里

目标：

- 不改变整体能力
- 先消除 resolver core 对 SQL 的直接依赖

做法：

- 抽出 `MetadataSource`
- 用现有数据库实现一个 `IndexedMetadataSource`
- 让 `resolvelib provider` 只依赖接口

这是最小风险的第一步。

### 阶段 2: 提炼统一的 artifact inspector

目标：

- 收敛依赖提取逻辑
- 避免后面 live/indexed 两套逻辑分叉

做法：

- 合并 archive 选择逻辑
- 合并 `setup.py / setup.cfg / pyproject.toml` 的解析入口
- 让 inspector 只输出 dependency metadata

### 阶段 3: 增加 `LiveMetadataSource`

目标：

- 让 resolver 在没有数据库时也能工作

做法：

- 查询远端版本列表
- 下载并解析候选发行包
- 接入本地缓存

### 阶段 4: 引入 indexer

目标：

- 复用与 `live` 相同的 inspector 做离线预提取
- 为 `indexed` 提供统一的 dependency metadata 数据入口

### 阶段 5: 接入容器运行时

做法：

- 新增 `runtime/pip_adapter.py`
- 替换 `resolver-pip` 的 placeholder entry
- 更新 `resolving/containerization/images/pip/Dockerfile`
- 更新 `docker-compose.yml`

## 11. 需要特别注意的风险

### 11.1 sdist 解析仍然会是最脆弱的部分

wheel 往往可以直接从 metadata 拿到 `Requires-Dist`，但 sdist 常常需要：

- 解压
- 找配置文件
- 解析 `setup.py`
- 处理动态逻辑

因此设计上要接受这个事实：

- `live` 模式的正确性上限取决于 inspector 对 sdist 的处理能力
- `indexed` 模式并不会消灭这个问题，只是把成本前移

### 11.2 两种模式不能维护两套解析规则

这是必须避免的。

如果 `live` 和 `indexed` 各自写一套依赖提取逻辑，后面一定会漂移。

正确做法应该是：

- 同一份 `artifact inspector`
- 两个 source 只决定“什么时候提取、从哪里读结果”

### 11.3 不要把 PostgreSQL 细节泄漏回 resolver core

例如下面这些都应该被隔离在 store 层：

- Peewee model
- SQL 语句
- 连接池
- PostgreSQL 特定索引设计

## 12. 最终建议

如果以“既能长期维护，又方便别人快速上手”为目标，我建议最终定稿为下面这套策略：

1. 架构上彻底解除 resolver core 对数据库的绑定
2. 对外提供两种正式配置
   - `live`: 零前置依赖，慢
   - `indexed`: 需要预提取，快
3. 本次不引入模块路径提取与路径冲突检测能力
4. 复用同一套 artifact inspector，同时服务实时模式和预提取模式
5. 先以接口方式兼容现有数据库路径，再逐步补 live 模式和 indexer

## 13. 我认为最合理的结论

结合当前仓库状态，我认为 `pip` 重构不应该再沿用“EnvResolver 直接连数据库”的思路，而应该改成：

- `resolver core` 是稳定内核
- `metadata source` 是可替换边界
- `database` 只是一个可选加速后端

同时，这次迁移目标应该明确限定为“抽离 `EnvResolver` 的依赖解析能力”，而不是整体搬迁 `ModuleGuard`。

这样既能保住老方案的性能优势，也能提供一个不需要数据库的低门槛版本，符合当前 OpenDep 容器化架构，也能把本次实现范围控制在一个清晰、可落地的边界内。
