# resolving Gateway

This directory contains the gateway implementation used by the OpenDep resolver system.
It is the host-side orchestration layer that sits behind the repository-root `main.py` entrypoint.

## Purpose

The gateway is responsible for turning user-facing CLI requests into normalized resolver operations.
In practice, the code in `resolving/gateway/` is responsible for:

- parsing and validating gateway-level request data
- selecting the correct resolver entry from the registry
- checking command and format compatibility before launch
- invoking the configured backend launcher
- normalizing backend responses into the shared gateway schema
- producing consistent error handling and response envelopes

## Relationship to the top-level entrypoint

The user-facing CLI entrypoint is the repository-root `main.py` file.
That file imports the gateway modules from this directory and uses them to execute resolver commands.

This means:

- `main.py` is the only intended direct entrypoint for users
- `resolving/gateway/` is an implementation directory, not a standalone CLI directory
- the gateway code is shared by all configured resolver ecosystems

## Directory structure

Current gateway modules:

- `resolving/gateway/config.py` — configuration loading and default registry selection
- `resolving/gateway/contract.py` — request and response contract validation
- `resolving/gateway/dispatcher.py` — coordination of routing, process execution, and normalization
- `resolving/gateway/errors.py` — gateway-specific error types
- `resolving/gateway/models.py` — internal process result models
- `resolving/gateway/registry.py` — registry access and resolver lookup
- `resolving/gateway/response.py` — response normalization and response factory helpers
- `resolving/gateway/router.py` — command and capability-based resolver selection
- `resolving/gateway/runner.py` — process execution helpers
- `resolving/gateway/service.py` — top-level request handling service used by `main.py`

## Internal execution flow

A typical gateway request flows through this directory in the following order:

1. `main.py` parses CLI arguments and builds a request payload
2. `resolving/gateway/config.py` selects and loads the appropriate registry file
3. `resolving/gateway/registry.py` provides resolver metadata for the requested ecosystem
4. `resolving/gateway/router.py` validates command and format compatibility
5. `resolving/gateway/runner.py` launches the configured backend command
6. `resolving/gateway/response.py` validates and normalizes the backend response
7. `resolving/gateway/service.py` returns the final gateway response envelope

## Relationship to other directories

The gateway works together with several adjacent parts of the repository:

- `resolving/config/` provides resolver registry files selected by the gateway
- `resolving/spec/` provides the shared request and response specification documents
- `resolving/containerization/` provides Docker-based backend execution for the integrated ecosystems
- `main.py` exposes the user-facing CLI that calls into this gateway implementation

## Notes

- This directory does not contain a separate executable entry script.
- The gateway remains ecosystem-agnostic; ecosystem-specific semantics belong in the backend adapters and native resolvers.
- The current integrated containerized ecosystems are `npm`, `maven`, `cargo`, and `go`.
