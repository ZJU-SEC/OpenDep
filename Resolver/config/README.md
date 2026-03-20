# Resolver Registry Configuration

This directory stores resolver registry files used by the gateway CLI and service layer.
Each registry declares which backend should handle a given ecosystem, how that backend is launched, and which capabilities the gateway can advertise before process startup.

## Files

- `Resolver/config/resolvers.container.yaml` — the primary registry for the current containerized resolver stack
- `Resolver/config/resolvers.yaml` — a legacy host-process registry kept for fallback and comparison

## Notes

- The files currently use JSON syntax even though they keep the historical `.yaml` suffix.
- `main.py` auto-selects the container registry when the requested ecosystem is available there.
- Registry paths are resolved by `Resolver/gateway/config.py`.
- Specification documents live under `Resolver/spec/`.
