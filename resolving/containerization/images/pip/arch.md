# resolving 当前架构梳理

本文档用于在重构 Python 后端 resolving 之前，先把当前 `resolving/` 子系统的实际架构、四个已接入生态（`maven`、`npm`、`cargo`、`go`）的实现方式，以及 `pip` 目前所处的位置理清楚。

## 1. 总体调用链路

当前项目的 resolver 是一个“宿主机 Python gateway + 容器内 Python adapter + 生态原生后端”的三层结构。

端到端链路如下：

```text
main.py
  -> resolving/gateway/
  -> resolving/config/resolvers.container.yaml
  -> resolving/containerization/docker_gateway_proxy.py
  -> docker compose run resolver-<ecosystem>
  -> resolving/containerization/runtime/<ecosystem>_adapter.py
  -> resolving/containerization/images/<ecosystem>/ 中的原生后端
  -> adapter 输出统一 JSON response
```

这条链路里最关键的设计点有两个：

1. `main.py` 和 `resolving/gateway/` 不直接理解各生态的依赖解析逻辑，它们只负责统一协议、路由、执行和错误包装。
2. 各生态真正的解析算法大多放在容器镜像里的原生后端中；Python adapter 只做“协议桥接”和“归一化”。

## 2. `resolving/` 目录职责拆分

### 2.1 顶层入口：`main.py`

`main.py` 是当前用户入口。它负责：

- 解析 CLI 参数，构造统一 request；
- 根据 ecosystem 自动选择 registry；
- 调用 `resolving.gateway.service.GatewayService`；
- 打印统一 response JSON。

`main.py` 的 `build_request()` 已经把 resolver 协议固定成一套跨生态请求格式：

- `command`: `resolve | list | health | capabilities`
- `ecosystem`
- `package.name / package.version`
- `options.format / options.timeout_ms / options.return_raw`

### 2.2 Gateway 层：`resolving/gateway/`

这是宿主机侧的统一调度层。

核心模块职责如下：

- `contract.py`
  - 校验 request/response 是否符合统一协议。
- `registry.py`
  - 从 registry 中按 ecosystem 找 resolver。
- `router.py`
  - 检查 command 和 format 是否在该 resolver 的 capabilities 中。
- `runner.py`
  - 用 `subprocess.run()` 执行 registry 中声明的命令。
- `response.py`
  - 把子进程 stdout 解析为 JSON，二次校验 response，并在需要时保留 raw stdout/stderr。
- `service.py`
  - 顶层入口，串起 validate -> dispatch -> normalize。
- `dispatcher.py`
  - 连接 router、runner、normalizer。

这层是完全 ecosystem-agnostic 的。它知道“如何调用 resolver”，但不知道“如何解析 npm/go/maven/cargo 依赖”。

### 2.3 Registry 层：`resolving/config/`

当前有两份 registry：

- `resolving/config/resolvers.container.yaml`
- `resolving/config/resolvers.yaml`

实际生效的是前者。

原因有两个：

1. `resolving/gateway/config.py` 的 `default_config_path()` 会优先选择 `resolvers.container.yaml`。
2. `resolvers.yaml` 里指向的老路径，如：
   - `resolving/pip-dependency-resolver/adapter_main.py`
   - `resolving/maven-dependency-resolver/adapter_launcher.py`
   - `resolving/go-dependency-resolver/adapter_launcher.py`
   - `resolving/cargo-dependency-resolver/adapter_launcher.py`
   - `resolving/js-dependency-resolver/adapter_launcher.py`

   在当前仓库里都不存在，说明这份 host/process registry 属于历史遗留配置，不能作为当前重构的真实落点。

因此，如果今天要重构 Python 的 `pip` 后端，应该对齐的是 container path，而不是 `resolvers.yaml`。

### 2.4 统一协议：`resolving/spec/`

这里定义的是跨生态共享的 request/response contract。

重点包括：

- 请求 schema：`resolving/spec/request.schema.json`
- 响应 schema：`resolving/spec/response.schema.json`
- 错误码 taxonomy：
  - `INVALID_ARGUMENT`
  - `UNSUPPORTED_COMMAND`
  - `UNSUPPORTED_ECOSYSTEM`
  - `UNSUPPORTED_OPTION`
  - `PACKAGE_NOT_FOUND`
  - `VERSION_NOT_FOUND`
  - `RESOLUTION_CONFLICT`
  - `DATA_SOURCE_UNAVAILABLE`
  - `BACKEND_MISCONFIGURED`
  - `TIMEOUT`
  - `BACKEND_CRASHED`
  - `PROTOCOL_ERROR`
  - `INTERNAL_ERROR`

对后续 Python backend 来说，最重要的约束是：

- 成功时要返回统一 envelope；
- `resolve` 结果最好归一成 `root / nodes / edges / semantics / metrics`；
- 如果需要保留原始后端输出，使用 `raw`，而不是直接污染统一 `result`。

## 3. 容器层的职责分布

`resolving/containerization/` 里其实又分成三层。

### 3.1 宿主机到 Docker 的桥：`docker_gateway_proxy.py`

这个脚本由 gateway 调用，本质上是一个 Docker Compose proxy：

- 从 stdin 读取 gateway request；
- 执行：

  ```text
  docker compose run --rm --no-deps -T resolver-<ecosystem>
  ```

- 把容器 stdout 原样回传给 gateway；
- 如果容器在输出 JSON 前就失败，则包装成 infra error。

它不做生态逻辑，只做“把请求送进容器”。

### 3.2 Compose 服务定义：`docker-compose.yml`

当前服务如下：

- `resolver-pip`
- `resolver-npm`
- `resolver-maven`
- `resolver-cargo`
- `resolver-go`

其中：

- `pip` 是占位服务；
- `npm`、`maven`、`cargo`、`go` 是当前真实接入的四个 resolver。

Compose 负责把每个生态的：

- image build 目录
- adapter entrypoint
- 环境变量
- cache volume

绑定在一起。

### 3.3 容器内 adapter 层：`resolving/containerization/runtime/`

这层是当前整个容器化架构的关键抽象。

共享工具主要有两个：

- `adapter_runtime.py`
  - 定义 `AdapterMetadata`
  - 从 stdin 读取 request
  - 复用 gateway 的 `validate_request`
  - 统一处理 `health` / `capabilities`
  - 统一生成 success/error response envelope
- `launcher_normalization.py`
  - `ensure_graph_result()`，用于校验和补齐 graph 结果中的 `semantics`、`metrics`

当前 adapter 设计模式非常明确：

1. 容器 entrypoint 是 Python adapter，而不是原生后端二进制本身。
2. adapter 先处理公共命令 `health` 和 `capabilities`。
3. 真正 `resolve` 或 `list` 时，再去调用原生后端。
4. adapter 把原生后端的 stdout/stderr/exit_code 映射为统一协议。

这一点对未来 `pip` 重构最重要：即使 Python backend 本身也是 Python，仍然建议保留一个独立的 `pip_adapter.py`，把“统一协议层”和“pip 解析逻辑”分开。

## 4. 四个已接入生态的实现方式

虽然四个生态都走同一条容器链路，但它们的“原生后端输出形态”和“adapter 工作量”并不完全一样。

### 4.1 Maven

#### 镜像层

目录：`resolving/containerization/images/maven/`

构建方式：

- `Dockerfile` 基于 `cnspary/maven-resolver-base:latest`
- 安装 `maven` 和 `python3`
- 构建 `pom.xml`
- 产物：
  - `/usr/local/lib/maven-resolver.jar`
  - `/usr/local/bin/maven-resolver`（`run.sh`）

Compose 里真正使用的是 Python adapter：

```yaml
entrypoint: ["python3", "resolving/containerization/runtime/maven_adapter.py"]
```

也就是说，镜像虽然把 jar 安装成了原生命令，但容器启动时先进入 adapter。

#### Adapter 层

`maven_adapter.py` 负责：

- `health`：检查 `java` 和 jar 是否存在；
- `capabilities`：声明支持 `resolve/health/capabilities`、`graph`、`raw/scopes/managed-dependencies`；
- `resolve`：把
  - `package.name`
  - `package.version`

  拼成 Maven 坐标 `groupId:artifactId:version`；
- 调用：

  ```text
  java -cp /usr/local/lib/maven-resolver.jar cn.edu.zju.nirvana.adapter.MavenResolverAdapterMain <coordinate>
  ```

- 校验后端 JSON，再用 `ensure_graph_result()` 保证结果符合统一 graph 结构。

#### 原生后端层

Java 入口是：

- `cn.edu.zju.nirvana.adapter.MavenResolverAdapterMain`
- `cn.edu.zju.nirvana.adapter.MavenSingleResolver`

后端使用 Eclipse Aether / Maven resolving 相关能力：

- 读取 artifact descriptor；
- collect dependencies；
- 遍历 `DependencyNode`；
- 直接拼出统一风格的 graph JSON：
  - `root`
  - `nodes`
  - `edges`
  - `semantics`
  - `metrics`

#### 结论

Maven 属于“后端已经直接输出统一 graph JSON，adapter 只做轻量包装”的类型。

### 4.2 npm

#### 镜像层

目录：`resolving/containerization/images/npm/`

构建方式：

- `Dockerfile` 基于 `cnspary/npm-resolver-base:latest`
- 安装 `cmake`、`libcurl4-openssl-dev`、`python3`
- 通过 CMake 编译 C++ 后端
- 产物：
  - `/usr/local/bin/npm-resolver`

Compose 中同样先进入 Python adapter：

```yaml
entrypoint: ["python3", "resolving/containerization/runtime/npm_adapter.py"]
```

#### Adapter 层

`npm_adapter.py` 是四个 adapter 里最“重”的一个。它不只是做 subprocess 包装，还承担了明显的协议翻译工作。

主要职责：

- `health`
  - 检查 C++ binary 是否存在；
  - 报告平台 profile（`os/cpu/libc`）。
- `capabilities`
  - 支持 `resolve/health/capabilities`；
  - `graph`；
  - `raw/peer-dependencies/directory-tree`。
- `resolve`
  - 调用：

    ```text
    /usr/local/bin/npm-resolver <name> <version>
    ```

  - 解析 C++ 后端的“混合 stdout 协议”：
    - 第一行是进度前缀 `Resolving:`；
    - 中间有 dependency tree JSON；
    - 还有 directory tree 文本；
    - 最后一行是 resolution state log。

- 把这些后端原始数据重新组装成统一 graph：
  - 解析 peer dependency 标记；
  - 解析 alias dependency；
  - 解析安装路径；
  - 把 directory tree 和 dependency tree 汇总成 `nodes/edges`；
  - 把后端状态 `Ok/Conflict/Empty/NpmError/...` 映射到统一错误码。

#### 原生后端层

C++ 入口是 `src/main.cpp`。

当前 CLI 非常简单：

```text
npm-resolver <name> <version>
```

它内部构造 `idealTree`，输出：

- 进度信息；
- 依赖树；
- 目录树；
- 最终状态日志。

这个后端并没有直接输出最终统一 JSON graph，因此 adapter 需要承担大量 normalization 工作。

#### 结论

npm 属于“后端输出是生态原生/半结构化数据，adapter 负责重归一化”的类型。  
如果未来 Python pip backend 也更容易先输出自己的中间结构，那么可以参考 npm 的接入模式。

### 4.3 Cargo

#### 镜像层

目录：`resolving/containerization/images/cargo/`

构建方式：

- `Dockerfile` 基于 `cnspary/cargo-resolver-base:latest`
- 安装 `python3`、`git`、`pkg-config`、`libssl-dev`、`ca-certificates`
- 复制 `.cargo/config.toml`
- 在镜像构建期间 clone `crates.io-index`
- 编译 Rust binary
- 产物：
  - `/usr/local/bin/cargo-resolver`

Compose 中为它挂了持久 volume：

- `/cargo-home`
- volume 名：`resolver-cargo-home-cache`

#### Adapter 层

`cargo_adapter.py` 负责：

- `health`
  - 检查 Python runtime、backend binary、`CARGO_HOME`、registry mode；
- `capabilities`
  - 支持 `resolve/health/capabilities`；
  - `graph/full`；
  - `raw/features/registry/cache`；
- `resolve`
  - 强制要求 `package.version`；
  - 调用：

    ```text
    /usr/local/bin/cargo-resolver resolve <name> <version> --format <graph|full>
    ```

  - 按 stderr 文本把错误分成：
    - `VERSION_NOT_FOUND`
    - `DATA_SOURCE_UNAVAILABLE`
    - `BACKEND_CRASHED`
  - 成功时对后端 JSON 调用 `ensure_graph_result()`。

#### 原生后端层

Rust 入口是 `src/bin/cargo_resolver.rs`。

它会：

- 解析 CLI 参数；
- 调用 `resolve_graph_of_version_once()`；
- 把 graph 直接序列化为 JSON。

真正的解析核心在 `src/resolver.rs`：

- 动态生成一个虚拟 `Cargo.toml`；
- 在临时 workspace 中调用 Cargo 内部解析逻辑；
- 先收集 feature，再用 `cargo::ops::resolve_with_previous` 做解析；
- 生成统一 graph 结果。

#### 结论

Cargo 也属于“原生后端已直接输出统一 graph JSON，adapter 主要负责参数校验、错误映射、健康检查”的类型。

### 4.4 Go

#### 镜像层

目录：`resolving/containerization/images/go/`

构建方式：

- `Dockerfile` 基于 `cnspary/go-resolver-base:latest`
- `go mod tidy`
- 编译 `cmd/go_resolver/main.go`
- 产物：
  - `/usr/local/bin/go-resolver`

Go 当前没有单独的命名 cache volume。

#### Adapter 层

`go_adapter.py` 是四个 adapter 里唯一同时支持 `resolve` 和 `list` 的一个。

主要职责：

- `health`
  - 检查 Python runtime、backend binary、`GO_PROXY_BASE_URL`；
- `capabilities`
  - 支持 `resolve/list/health/capabilities`；
  - `graph/full`；
  - `raw/replace/exclude/buildlist`；
- `resolve`
  - 调用：

    ```text
    /usr/local/bin/go-resolver resolve <module> <version> --format <graph|full>
    ```

- `list`
  - 调用：

    ```text
    /usr/local/bin/go-resolver list <module> <version> --json
    ```

- 把 backend stderr 中的错误前缀或关键词映射到统一错误码；
- `resolve` 时用 `ensure_graph_result()` 校验 graph；
- `list` 时把后端 JSON 包装到 `result.list`。

#### 原生后端层

Go 入口在 `cmd/go_resolver/main.go`。

它区分两个子命令：

- `resolve`
- `list`

内部核心逻辑在 `internal/resolver/resolver.go`，特点是：

- 通过 `internal/source` 从 Go proxy 拉取模块元数据；
- 解析 `go.mod`；
- 处理 replace/exclude；
- 使用 MVS（minimal version selection）构图；
- 由 `internal/output` 输出 graph 或 list JSON。

#### 结论

Go 属于“原生后端直接提供结构化 JSON，adapter 负责多命令分发和错误码映射”的类型。

## 5. 当前四个生态的共性与差异

### 5.1 共性

当前四个已接入 resolver 共享以下稳定模式：

1. 它们都通过 `resolvers.container.yaml` 注册到 gateway。
2. 它们都经由 `docker_gateway_proxy.py` 进入 Docker Compose 服务。
3. Compose 里真正的 entrypoint 都是 Python adapter。
4. adapter 都复用了 `adapter_runtime.py` 的统一 response envelope。
5. adapter 都负责：
   - `health`
   - `capabilities`
   - timeout/error 映射
   - raw 输出保留
6. 统一 graph 结果最终都要落在：
   - `root`
   - `nodes`
   - `edges`
   - `semantics`
   - `metrics`

### 5.2 差异

最大的差异不在 gateway，而在“原生后端输出的成熟度”：

- Maven / Cargo / Go
  - 原生后端已经能直接输出 JSON；
  - adapter 偏轻量。
- npm
  - 原生后端输出是带日志和中间结构的 stdout；
  - adapter 承担大量结果转换。

这给未来 pip 提供了两种实现路线：

1. Python backend 直接输出统一 graph JSON，仿照 Maven/Cargo/Go。
2. Python backend 先输出 pip 原生/中间结构，再由 `pip_adapter.py` 转成统一 graph，仿照 npm。

如果目标是后续维护简单、测试面清晰，我更倾向第一种。

## 6. `pip` 当前状态

以下内容最初记录的是重构前的 placeholder 状态。
当前仓库中，`pip` 已经接入真实 backend；这里保留旧状态是为了说明迁移前基线。

重构前，`resolving/containerization/images/pip/` 只有一个 `Dockerfile`：

```dockerfile
FROM python:3.12-slim
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1
LABEL resolver.ecosystem="pip"
LABEL resolver.stage="placeholder"
CMD ["python", "resolving/containerization/runtime/default_adapter.py"]
```

这说明在重构启动前，`pip` 的状态不是“老实现已经容器化”，而是“容器 wiring 已经打通，但真实后端还没接进来”。

重构前，对应的 Compose 服务 `resolver-pip` 也是 placeholder：

- image 使用 `resolving/containerization/images/pip/Dockerfile`
- entry command 使用 `resolving/containerization/runtime/default_adapter.py`
- `PLACEHOLDER_MESSAGE` 明确写着需要替换成真实 backend

因此，这次 Python backend 重构本质上不是“改已有 pip 容器内后端”，而是“首次把真正的 pip backend 放到当前容器化架构里”。

## 7. Python `pip` 后端后续应接入的位置

结合四个现有生态的实现，我建议新的 Python pip resolver 对齐下面这套结构：

### 7.1 推荐目录形态

建议新增：

- `resolving/containerization/images/pip/`
  - Python backend 源码
  - `Dockerfile`
  - 可选 `README.md`
- `resolving/containerization/runtime/pip_adapter.py`

不要继续长期依赖 `default_adapter.py`。

### 7.2 推荐职责边界

#### `pip_adapter.py` 应负责

- 读取 stdin request；
- 处理 `health` / `capabilities`；
- 调用真正的 Python pip backend CLI 或模块入口；
- 做 timeout / stderr / exit_code 到统一错误码的映射；
- 在需要时保留 `raw`；
- 把结果封装成统一 response envelope。

#### Python pip backend 应负责

- 真正的依赖解析逻辑；
- 最好直接输出统一 graph JSON；
- 至少输出稳定、可机读的 JSON，而不是混合日志 stdout。

### 7.3 推荐优先级

如果今天开始落地，我建议优先按下面顺序推进：

1. 先复用现有 adapter 架构，补一个真正的 `pip_adapter.py`。
2. 再把 Python pip resolver 后端放进 `resolving/containerization/images/pip/`。
3. 让后端先稳定输出 JSON graph。
4. 最后更新：
   - `resolving/containerization/images/pip/Dockerfile`
   - `resolving/containerization/docker-compose.yml`
   - 如有必要，补 `README.md` 和示例请求/响应。

## 8. 对重构最重要的结论

为了避免后续设计跑偏，这里把最关键的结论单独列出来：

1. 当前真实架构的中心不是旧的本地 process resolver，而是 container-first 架构。
2. `resolvers.yaml` 是历史遗留，且目标脚本在仓库中已经不存在，不应作为新的 Python 重构基线。
3. 当前稳定抽象边界是：
   - gateway 负责统一入口与协议校验；
   - docker proxy 负责进入容器；
   - Python adapter 负责协议桥接；
   - 原生后端负责生态依赖解析。
4. 在重构启动前，`pip` 只有 placeholder，没有真实 backend；当前仓库状态已经完成该接入。
5. 新的 Python pip resolver 最自然的接入点是：
   - 在 `resolving/containerization/images/pip/` 中放真实后端；
   - 在 `resolving/containerization/runtime/pip_adapter.py` 中对齐现有 adapter 模式。
6. 如果可行，优先让 pip backend 直接输出统一 graph JSON，这样整体维护成本最低。
