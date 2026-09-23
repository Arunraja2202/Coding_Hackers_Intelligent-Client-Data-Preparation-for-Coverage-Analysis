# Architecture

Browser -> FastAPI -> Job Service -> Profiler -> CSI LLM -> Deterministic Transformer -> Artifacts -> SQLite history.

The LLM is used for semantic interpretation: header rows, dataset shape, target mappings, period strategy, matrix detection, transformations, confidence and review flags. Deterministic code owns data movement and output generation. This prevents an LLM response from directly writing client data without validation.

For large files, the engine selector routes files above 1 GiB to PySpark. The UI polls a persisted SQLite job record so the browser can be closed and the job can continue in the server process.
