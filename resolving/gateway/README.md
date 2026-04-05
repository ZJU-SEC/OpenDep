# resolving Gateway

`resolving/gateway/` is the host-side orchestration layer behind the repository-root `main.py` entrypoint.

## What It Does

The gateway is responsible for:

- validating and normalizing incoming request data
- loading the active resolver registry
- checking command and format compatibility before launch
- selecting the correct resolver for the requested ecosystem
- invoking the configured backend launcher
- normalizing backend output into the shared response envelope

## Request Flow

A typical request passes through the gateway in this order:

1. `main.py` parses CLI arguments and builds a request payload.
2. [`resolving/gateway/config.py`](config.py) loads the active registry file, and `main.py` builds a [`resolving/gateway/registry.py`](registry.py) `ResolverRegistry` from it.
3. [`resolving/gateway/service.py`](service.py) validates the request through [`resolving/gateway/contract.py`](contract.py).
4. [`resolving/gateway/dispatcher.py`](dispatcher.py) selects resolver metadata through [`resolving/gateway/registry.py`](registry.py) and validates command and format support through [`resolving/gateway/router.py`](router.py).
5. [`resolving/gateway/runner.py`](runner.py) launches the configured backend command.
6. [`resolving/gateway/response.py`](response.py) validates and normalizes the backend response.
7. [`resolving/gateway/service.py`](service.py) returns the final response envelope.

## Relationship to Adjacent Directories

- [`resolving/config/README.md`](../config/README.md) provides the resolver registry files
- [`resolving/spec/README.md`](../spec/README.md) defines the shared request and response contract
- [`resolving/containerization/README.md`](../containerization/README.md) provides the current container-backed resolver services
