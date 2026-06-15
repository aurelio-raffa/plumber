"""Orchestrator for the analysis pipeline. All the workflow is included in a single Python program that looks at the
results of each step and decides what to submit next using custom code.

Lazy execution (opt-in via the ``lazy`` flag at the top of the pipeline YAML, overridable per stage): a stage is
skipped when its code state, parameters and inputs match a previously recorded successful run (tracked in the MLflow
store) whose outputs are still present and byte-identical on disk. When a stage *is* executed with unchanged
code+inputs+params but yields a different output, that non-determinism is warned about (or raised, if
``ensure_determinism`` is on). Every stage is additionally seeded deterministically (see src/utils/seeding.py).
"""
import os
import json
import sys
import logging
import mlflow

from fire import Fire


from __init__ import root_path, console_handler
from src.utils.io.parse_config import parse_config
from src.utils.io import lazy
from src.utils.banner import make_banner

logger = logging.getLogger(__name__)
logger.addHandler(console_handler)
# surface the lazy module's warnings (skipped byte-exact checks, degraded code-state) on the console too
lazy.logger.addHandler(console_handler)


def _coerce_bool(value, default: bool) -> bool:
    """Interpret a YAML scalar (or None) as a boolean, falling back to ``default`` when unset."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _log_metrics_to_run(tracking_client, run_id: str, metrics_path: str) -> dict:
    """Read a stage's flat metrics JSON and log each scalar to the given run; return the metrics dict."""
    with open(metrics_path) as handle:
        metrics = json.load(handle)
    for key, value in metrics.items():
        tracking_client.log_metric(run_id=run_id, key=key, value=value)
    return metrics


def run(config_file: str):
    # read pipeline config files
    # WARNING: experimental
    # TODO: find a way to keep track of parameters specified through environment variables
    config = parse_config(os.path.join(root_path, config_file))

    # run parameters
    project_uri = config['project_uri']
    log_artifacts = config['log_artifacts']
    log_models = config['log_models']
    tags = config['tags']

    # welcome banner: repo name (from the project directory) + version (from the pipeline tags) + optional
    # description; the name and subtitle are length-capped so the banner never overextends horizontally.
    # Disable it entirely with `banner: false` at the top of the pipeline YAML; pick a different FIGlet font
    # with `banner_font: <name>` (fonts other than the bundled `small` require pyfiglet to be installed).
    if _coerce_bool(config.get('banner'), True):
        print(make_banner(
            name=os.path.basename(root_path),
            version=str(tags.get('version', '')) if isinstance(tags, dict) else '',
            tagline=str(config.get('description', '')),
            font=str(config.get('banner_font', 'small')),
        ), file=sys.stderr)

    # lazy-execution / determinism settings (both default to off => behaviour identical to before)
    lazy_default = _coerce_bool(config.get('lazy'), False)
    determinism_default = _coerce_bool(config.get('ensure_determinism'), False)
    file_max = int(config.get('lazy_content_max_file_mb', 256)) * 1024 ** 2
    dir_max = int(config.get('lazy_content_max_dir_mb', 2048)) * 1024 ** 2

    tracking_client = mlflow.tracking.MlflowClient()
    code_hash = lazy.code_state_hash(root_path)     # whole-repo code state, computed once per pipeline run

    # start the main run and all secondary runs
    with mlflow.start_run() as orchestrator:
        # logging the configuration and tags for the run
        mlflow.log_artifact(config_file)
        mlflow.set_tags(tags)
        experiment_id = orchestrator.info.experiment_id

        # step by step execution
        total_steps = len(config['stages'])
        for i, stage in enumerate(config['stages']):
            for stage_name, parameters in stage.items():
                parameters = dict(parameters) if parameters else {}

                # per-stage overrides for lazy/determinism, popped so they never reach the stage's Fire CLI
                stage_lazy = _coerce_bool(parameters.pop('lazy', None), lazy_default)
                stage_determinism = _coerce_bool(parameters.pop('ensure-determinism', None), determinism_default)

                print(file=sys.stderr)
                print(f'==============> Stage {i + 1}/{total_steps}: "{stage_name}" '.ljust(103, '='), file=sys.stderr)

                # deterministic per-stage seed (from code + parameters; independent of input bytes, so cheap and
                # active even with lazy off). The stage subprocess inherits PIPELINE_SEED and seeds on import.
                params_hash_value = lazy.params_hash(parameters)
                os.environ['PIPELINE_SEED'] = str(lazy.stage_seed(code_hash, params_hash_value))

                # the setup stage is a cheap idempotent prerequisite (it creates the output dirs the other stages
                # depend on): never cached, but still seeded above.
                cacheable = stage_name != 'setup'
                # the fingerprint bookkeeping is only needed when lazy skipping or determinism checking is wanted
                active = cacheable and (stage_lazy or stage_determinism)

                cache_key = None
                cached = None
                inputs, outputs = ({}, {})
                if active:
                    inputs, outputs = lazy.classify_params(parameters, root_path)
                    inputs_fp = lazy.fingerprint_paths(inputs, root_path, file_max, dir_max, 'input')
                    cache_key = lazy.compute_cache_key(code_hash, params_hash_value, inputs_fp)
                    cached = lazy.find_cached_run(tracking_client, experiment_id, stage_name, cache_key)

                # ---- lazy hit: skip execution when the recorded outputs are still present and unchanged ----
                if stage_lazy and cached is not None and lazy.paths_present(outputs, root_path):
                    recorded = cached.data.tags.get(lazy.TAG_OUTPUT_FINGERPRINT)
                    current_fp = lazy.fingerprint_paths(outputs, root_path, file_max, dir_max, 'output')
                    if recorded is not None and recorded == current_fp:
                        logger.info('lazy: skipping "%s" (cache hit %s from run %s)',
                                    stage_name, cache_key[:12], cached.info.run_id)
                        tracking_client.set_tag(run_id=orchestrator.info.run_id,
                                                key=f'lazy_skipped_{stage_name}', value=cache_key[:12])
                        # keep the parent run's metric aggregation consistent with a freshly executed stage
                        if 'metrics-path' in parameters and os.path.exists(parameters['metrics-path']):
                            _log_metrics_to_run(tracking_client, orchestrator.info.run_id,
                                                parameters['metrics-path'])
                        continue
                    logger.warning('lazy: "%s" cache key matched but on-disk outputs differ from the recorded '
                                   'fingerprint; re-running', stage_name)

                # run stage (parameter logging is automatic)
                current_run = mlflow.run(
                    uri='',
                    entry_point=f'{project_uri}/{stage_name}.py',
                    parameters=parameters,
                    env_manager='local'
                )

                # log configurations as run artifacts
                if 'config-path' in parameters:
                    mlflow.log_artifact(parameters['config-path'])

                if 'metrics-config' in parameters:
                    mlflow.log_artifact(parameters['metrics-config'])

                if 'model-config' in parameters:
                    mlflow.log_artifact(parameters['model-config'])

                # artifact logging
                if log_artifacts and 'output-path' in parameters:
                    tracking_client.log_artifact(
                        run_id=current_run.run_id,
                        local_path=parameters['output-path']
                    )

                # tag the run with the model that was used for ease of access
                if 'model-type' in parameters:
                    tracking_client.set_tag(
                        run_id=current_run.run_id,
                        key='model-type',
                        value=parameters['model-type']
                    )
                    tracking_client.set_tag(
                        run_id=orchestrator.info.run_id,
                        key='model-type',
                        value=parameters['model-type']
                    )

                # metrics logging (metrics are logged in every run)
                if 'metrics-path' in parameters:
                    metrics = _log_metrics_to_run(tracking_client, current_run.run_id, parameters['metrics-path'])
                    # also logs metrics in the orchestrator run for ease of access
                    for key, value in metrics.items():
                        tracking_client.log_metric(
                            run_id=orchestrator.info.run_id,
                            key=key,
                            value=value
                        )

                # report logging
                if 'report-path' in parameters:
                    tracking_client.log_artifact(
                        run_id=current_run.run_id,
                        local_path=parameters['report-path']
                    )

                # model logging (ust saves it as artifact)
                # TODO: figure out how to store via log_model (temporarily stores them as artifact)
                if log_models:
                    # TODO: find a better convention for the parameters
                    # logging the vectorizer
                    if stage_name == 'preprocess' and 'vectorizer-path' in parameters:
                        tracking_client.log_artifact(
                            run_id=current_run.run_id,
                            local_path=parameters['vectorizer-path']
                        )
                    # logging the model
                    if stage_name == 'train_evaluate' and 'output-path' in parameters:
                        tracking_client.log_artifact(
                            run_id=current_run.run_id,
                            local_path=parameters['output-path']
                        )

                # ---- lazy bookkeeping + determinism guard (record this run's fingerprints) ----
                if active:
                    output_fp = lazy.fingerprint_paths(outputs, root_path, file_max, dir_max, 'output')
                    if cached is not None:
                        recorded = cached.data.tags.get(lazy.TAG_OUTPUT_FINGERPRINT)
                        if recorded is not None and recorded != output_fp:
                            message = (
                                f'Non-deterministic stage "{stage_name}": identical code, parameters and inputs '
                                f'produced a different output (recorded {recorded[:16]}..., now {output_fp[:16]}...).'
                            )
                            if stage_determinism:
                                raise RuntimeError(message)
                            logger.warning(message)
                    for key, value in (
                        (lazy.TAG_STAGE, stage_name),
                        (lazy.TAG_CACHE_KEY, cache_key),
                        (lazy.TAG_CODE_STATE, code_hash),
                        (lazy.TAG_PARAMS_HASH, params_hash_value),
                        (lazy.TAG_OUTPUT_FINGERPRINT, output_fp),
                    ):
                        tracking_client.set_tag(run_id=current_run.run_id, key=key, value=value)


if __name__ == '__main__':
    Fire(run)
