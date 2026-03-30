"""Entrypoint for the entire MLflow project run with remote tracking server
"""
import os
import mlflow

from fire import Fire


def run_project(
        config_file: str,
        experiment_name: str,
        mongodb_host: str = None,
        experiments_db: str = None,
        tracking_uri: str = None
):
    """Runs the project specified by the config_file as an experiment under the name experiment_name,
    with options to use a remote tracking server and experiment DB for intelligent execution.
    
    config_file (str): The path to the configuration file for the experiment
    experiment_name (str): A name for the type of experiment
    mongodb_host (str = None): The connection string to a MongoDB instance to track the execution of individual
        pipeline stages and avoid duplicate execution
    experiments_db (str = None): The DB name under which the experiments are to be recorded (if shared among different
        users operating on local machines, it is highly recommended choosing different values to avoid conflicts)
    tracking_uri (str = None): The connection string to a remote MLflow tracking server
    """
    # input parameters validation
    if tracking_uri is not None:
        # set the remote URI of the tracking server
        msg = f'Using remote MLflow tracking server at {"*" * (len(tracking_uri) - 3) + tracking_uri[-3:]} (redacted)'
        mlflow.set_tracking_uri(tracking_uri)
    else:
        msg = f'Using local MLflow tracking server (localhost)'
    # TODO: convert to logs
    print(msg)

    # setting up lazy execution
    if mongodb_host is not None and experiments_db is not None:
        # setup connection with the MongoDB instance
        os.environ['MONGODB_HOST'] = mongodb_host
        os.environ['MONGODB_EXPERIMENTS_DB_NAME'] = experiments_db
        msg = 'Lazy execution enabled for the current run, attempting connection MongoDB instance at ' \
              f'{"*" * (len(mongodb_host) - 3) + mongodb_host[-3:]} (redacted)'
    else:
        os.environ['LAZY_EXECUTION'] = 'disable'
        msg = 'Lazy execution disabled for the current run'
    print(msg)

    mlflow.projects.run(
        uri=os.path.dirname(os.path.abspath(__file__)),
        entry_point='src/stages/run.py',
        parameters={'config-file': config_file},
        experiment_name=experiment_name,
        env_manager='local'
    )


if __name__ == '__main__':
    Fire(run_project)
