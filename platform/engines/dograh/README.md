# Dograh engine (pinned, read only)

NEXORA uses Dograh as its voice engine without forking it. Dograh and its Pipecat fork are
cloned **read only** at the commits in `ENGINE.lock`; NEXORA's changes are patch files in
`patches/`, applied to a clean checkout at build time. Nothing is ever pushed to
`Sufi1512/dograh` or `dograh-hq/pipecat`.

Spec: `../../docs/P0_SPEC.md`, decisions: `../../docs/P0_IMPLEMENTATION_DECISIONS.md`,
tickets: `../../docs/P0_TICKETS.md`.

| File | What it does |
|---|---|
| `ENGINE.lock` | Repository URLs and full commit SHAs of Dograh and Pipecat |
| `fetch.sh <dir>` | Clones both at the pinned commits and applies `patches/`; fails if a patch no longer applies |
| `setup.sh <dograh-dir> <venv> <wheel>` | Python 3.13 venv with Dograh's API requirements, the pinned Pipecat fork and the nexora-audio wheel (no `[pipecat]` extra) |
| `run-tests.sh <dograh-dir> <venv>` | Dograh's own noise-reduction and workflow-configuration tests, then NEXORA's tests in `tests/` |
| `nexora.env` | NEXORA's Dograh settings: telemetry off, OSS mode, no PostHog key |
| `patches/0001-nexora-noise-engine.patch` | Adds the `nexora` noise engine (nexora-audio) next to RNNoise |
| `tests/` | NEXORA's tests, run against the patched Dograh |

## Run it locally (Linux x86-64)

```bash
cd platform/engines/dograh
(cd ../../../nexora-audio && python -m build --wheel)        # or: uv build --wheel
./fetch.sh /tmp/dograh
./setup.sh /tmp/dograh /tmp/dograh-venv ../../../nexora-audio/dist/nexora_audio-*.whl
./run-tests.sh /tmp/dograh /tmp/dograh-venv
```

`patches/0001-nexora-noise-engine.patch` is the same file as
`integrations/dograh/0001-nexora-noise-engine.patch` (a test checks they stay identical until
the old copy is removed).
