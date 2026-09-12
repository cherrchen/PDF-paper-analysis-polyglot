# Storage

[中文](./storage.md) | [English](./storage.en.md)

Persistent object storage, artifact layout, and dataset hosting are **intentionally unresolved**.

`run_pipeline` today writes canonical JSON and a viewer revision into the caller’s directory; that is not a versioned product workspace. M8 v1 batch A will close the local workspace convention; until then do not treat the on-disk layout as a stable storage API. Plan: [`docs/development/m8.en.md`](../development/m8.en.md).

Keep Git history small. Do not commit a large PDF corpus. A future external dataset system requires a testing or architecture Agent Note.
