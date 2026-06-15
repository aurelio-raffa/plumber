# Plumber

**A minimalistic ML pipeline template**

## Installation

Once you instantiate the template and clone the repository, install [`git lfs`](https://git-lfs.com/).
You can find the default options in the [`.gitattributes`](.gitattributes) file.

It is highly recommended to create a Python environment (3.11+) via `conda` or `Pipenv` for versioning.

## Usage

This template is intended for pipeline execution with [MLflow](https://mlflow.org/).
Pipelines are a tool for tracking the execution of code _while_ you develop.
To use the pipelines effectively, follow these few recommendations and your best judgement:
1. commit your code frequently, especially before running a pipeline;
2. break down your code into consecutive "stages", with obvious inputs and outputs;
3. version input data, your environment(e.g.: via
[`conda export`](https://docs.conda.io/projects/conda/en/stable/commands/export.html) and subsequent 
commit), and optionally the outputs;
4. seed **everything**.

The intended usage paradigm for the repository is build one or more pipelines in a readable `YAML` format
which contain all necessary specification to reproduce your results exactly
(see the [`hello_world.yaml`](config/hello_world.yaml) example).

### General Pipeline (Recommended) Structure
The `YAML` file should contain some boilerplate (used by the 
[`run_project.py`](run_project.py) and [`run.py`](src/stages/run.py) scripts to execute the pipeline), and under the 
`stages` attribute, a list of executable names under `scr/stages` without extensions (e.g.: `hello_world` to execute
[`src/stages/hello_world.py`](src/stages/hello_world.py)), each with a specification of the input arguments (use `{}`
if there are no inputs to a stage).

See the following pseudocode example.
```yaml
project_uri: 'src/stages'                                                           # the path of the directory where each stage scrip is saved
log_artifacts: false                                                                # whether to log the output file/directory as artifact
log_models: false                                                                   # whether to log the output model
lazy: false                                                                         # (optional) skip stages whose code + params + inputs are unchanged
ensure_determinism: false                                                           # (optional) raise instead of warn on non-deterministic outputs

stages:
    - <YOUR SCRIPT NAME>: {<A DICT OF OPTIONS, SUCH AS INPUT AND OUTPUT SPECIFICATIONS>}
    - <SCRIPT NAMES CAN BE REPEATED>:
        OPTIONS: CAN EVEN
        BE: EXPANDED
    - <ANOTHER SCRIPT NAME>: 
        REPLACE-UNDERSCORES-WITH-HYPHENS: IF YOU USE THE FIRE PACKAGE
    
tags:                                                                               # tags to be applied to the run
    version: 1.0
```

### Lazy Execution and the Determinism Guard

Two optional top-level flags (placed right after the boilerplate, both default `false`) make re-running a
pipeline cheap and reproducibility-checked — backed entirely by the MLflow store, so no extra database is needed:

- **`lazy`** — before running a stage the orchestrator computes a *cache key* from (a) the whole-repo code state
  (git `HEAD` + working-tree diff + untracked files), (b) the stage's parameters and (c) checksums of its input
  files/folders. If a previously recorded **successful** run has the same cache key and its outputs are still
  present and byte-identical on disk, the stage is **skipped**. The cache key and an output fingerprint are stored
  as tags on each stage's MLflow run.
- **`ensure_determinism`** — when a stage *is* executed with an unchanged cache key but produces a **different**
  output than last recorded, that is non-deterministic behaviour. By default it is logged as a warning; set this to
  `true` to raise an exception instead.

Both are **overridable per stage** by adding a `lazy:` / `ensure-determinism:` key inside that stage's parameter
block (the orchestrator strips these before invoking the stage's CLI). Checksums are *hybrid*: small files are
content-hashed (byte-exact) while very large files/directories fall back to a size-only manifest — a skipped
byte-exact check is logged, and the thresholds are tunable via `lazy_content_max_file_mb` /
`lazy_content_max_dir_mb`. Because the code state is the whole-repo dirty diff, **any** uncommitted edit busts the
caches (conservative by design — commit before relying on lazy hits). Laziness applies only to the orchestrator;
running a stage directly via its own CLI always executes it.

The convention is that the keys in `OUTPUT_PARAM_KEYS` (`output-path`, `metrics-path`, `report-path`) are treated
as a stage's outputs and any other parameter resolving to an existing path is an input — see
[`src/utils/io/lazy.py`](src/utils/io/lazy.py). A `setup` stage (see [`src/stages/setup.py`](src/stages/setup.py),
the recommended stage that creates the output directories) is never cached.

### Deterministic Seeding

Recommendation #4 above ("seed **everything**") is automated: every stage is seeded deterministically before its
body runs, with a seed derived from its code state + parameters (so a fixed config reproduces the same run). The
orchestrator exports it as the `PIPELINE_SEED` environment variable and the auto-hook in
[`src/stages/__init__.py`](src/stages/__init__.py) applies it via
[`src/utils/seeding.py`](src/utils/seeding.py), which seeds Python's `random` plus `numpy` / `torch` /
`lightning` **when those libraries are present** (absent ones are skipped). A stage's own seeding (e.g. an
explicit `seed:` parameter) still applies on top of this baseline.

### Plotting

[`src/utils/plotting`](src/utils/plotting) bundles a small, opinionated matplotlib setup: it registers the bundled
Inter font ([`data/fonts/inter`](data/fonts/inter)) as the global font, exposes colour-blind-safe IBM/Tol
palettes and ready-made linear/diverging colormaps ([`palettes.py`](src/utils/plotting/palettes.py)), and provides
`show_plot_and_save(...)` for displaying + persisting a figure with a templated filename. Importing
`src.utils.plotting.palettes` also sets the default axis colour cycle. Requires `matplotlib`.

### Individual Stages
Each stage should be thought of as an independent command-line script that does one "block" of the pipeline and stores 
the results to disk; it is highly recommended to save all outputs in an `outputs` directory.

To wrap the function defined in an appropriate stage file under `src/stages` into a CLI, it is highly recommended to use
the `fire` package.

Notice that each stage is run from within the `scr/stages` folder, so it should handle imports accordingly;
it is recommended to always include the statement:
```python
from __init__ import root_path
```
before importing anything else from within the `src` directory.
See an example below.

```python
# stage "do something": src/stages/do_something.py
from fire import Fire

from __init__ import root_path
# === other src imports go below this line ===
from src.something import some_function

def do_something():
    ...


if __name__ == '__main__':
    Fire(do_something)
```
> Notice that PyCharm will often interpret these imports as an error, so do not panic if you see them highlighted 
> in red.

### Running a Pipeline

The [`run_project.py`](run_project.py) script parses a `YAML` file in the correct format, launches an MLflow 
orchestrator runner and each stage as a further runner (all locally by default) based on the provided options.
Anything that can run as a command-line python script with the provided options as command-line arguments can be
executed, but it is highly recommended to use `fire` to handle wrapping.

Once you are ready to launch a pipeline, you can run `run_project.py` from the root of the directory with two inputs:
1. the path of the `YAML` script of the pipeline;
2. an experiment name, so that MLflow can save all similar runs under one name.

For example, to run `my_pipeline.yaml` (it is recommended to always keep pipelines under the `config` 
dir.) from a terminal, go to the root of the repository and execute:
```shell
run_project.py config/my_pipeline.yaml AN_EXPERIMENT_NAME
```

> It is highly recommended to only run pipelines after committing the changes to the code, since MLflow also saves
> the commit hash for full reproducibility.

At start-up the orchestrator prints a welcome banner with the repository name (derived from the project directory,
so it auto-rebrands when you instantiate the template) and the version read from the pipeline's `tags.version`,
plus an optional one-line `description` from the pipeline YAML. The ASCII art is produced by a small, dependency-free
FIGlet renderer ([`src/utils/banner.py`](src/utils/banner.py) + the bundled
[`data/fonts/small.flf`](data/fonts/small.flf), whose smushing logic is adapted from the
[FIGfont spec](http://www.jave.de/figlet/figfont.html) and the [`pyfiglet`](https://github.com/pwaller/pyfiglet)
reference implementation); the name and subtitle are length-capped so the banner never overextends horizontally,
and it degrades gracefully to a plain box if the font cannot be loaded.

- **Disable it** with `banner: false` at the top of the pipeline YAML.
- **Customize the font:** `pip install pyfiglet` for greater customizability, then set `banner_font: <name>` to any of
  the hundreds of FIGlet fonts pyfiglet ships (without pyfiglet only the bundled `small` font is available).

```
╭────────────────────────────────────────────────╮
│        _            _                          │
│   _ __| |_  _ _ __ | |__  ___ _ _              │
│  | '_ \ | || | '  \| '_ \/ -_) '_|             │
│  | .__/_|\_,_|_|_|_|_.__/\___|_|               │
│  |_|                                           │
│                                                │
│  v1.0  ·  A minimalistic ML pipeline template  │
╰────────────────────────────────────────────────╯
```

## Miscellaneous

1. [`git lfs`](https://git-lfs.com/) will not handle large files if you install it and track them _after_ committing
them, so beware!