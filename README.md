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

## Miscellaneous

1. [`git lfs`](https://git-lfs.com/) will not handle large files if you install it and track them _after_ committing
them, so beware!