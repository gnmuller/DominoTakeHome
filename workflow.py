from flytekit import workflow
from flytekitplugins.domino.task import DominoJobConfig, DominoJobTask

@workflow
def worker1_workflow():
    lab1 = DominoJobTask(
        name='Lab 1',
        domino_job_config=DominoJobConfig(Command="python worker1.py"),
        use_latest=True
    )
    lab2 = DominoJobTask(
        name='Lab 2',
        domino_job_config=DominoJobConfig(Command="python worker1_lab2.py"),
        use_latest=True
    )
    lab3 = DominoJobTask(
        name='Lab 3',
        domino_job_config=DominoJobConfig(Command="python worker1_lab3.py"),
        use_latest=True
    )
    lab1()
    lab2()
    lab3()
