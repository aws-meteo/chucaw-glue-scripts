# FourCastNet Docs Index

This folder consolidates FourCastNet development docs for local validation and cleanup.

## Files
- `preprocessing.md`: preprocessing contract and local/Glue operational flow.
- `colab_smoke_test.md`: tensor-first Colab smoke test guidance.
- `artifact_inventory.md`: inventory of source, tests, docs, and generated artifacts.
- `cleanup_commit_plan.md`: proposed 5 semi-atomic commit groups (no commits created here).

## Core reminders
- Tensor-first is the primary smoke path.
- HDF5 support remains available but optional.
- `compatibility_fixture` outputs are explicitly `NOT_SCIENTIFICALLY_VALID`.
- Strict mode is the scientific target.
- Real FourCastNet execution requires real checkpoint/stats/backend integration.
