"""Orchestrator for the analysis pipeline. All the workflow is included in a single Python program that looks at the
results of each step and decides what to submit next using custom code.
"""
import os
import json
import sys
import mlflow

from fire import Fire


from __init__ import root_path
from src.utils.io.parse_config import parse_config


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
    tracking_client = mlflow.tracking.MlflowClient()

    # start the main run and all secondary runs
    with mlflow.start_run() as orchestrator:
        # logging the configuration and tags for the run
        mlflow.log_artifact(config_file)
        mlflow.set_tags(tags)

        # step by step execution
        total_steps = len(config['stages'])
        for i, stage in enumerate(config['stages']):
            for stage_name, parameters in stage.items():
                print(file=sys.stderr)
                print(f'==============> Stage {i + 1}/{total_steps}: "{stage_name}" '.ljust(103, '='), file=sys.stderr)

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
                    with open(parameters['metrics-path']) as handle:
                        metrics = json.load(handle)

                    # saves each metric as key-value pair
                    for key, value in metrics.items():
                        tracking_client.log_metric(
                            run_id=current_run.run_id,
                            key=key,
                            value=value
                        )
                        # also logs metrics in the orchestrator run for ease of access
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


if __name__ == '__main__':
    Fire(run)
