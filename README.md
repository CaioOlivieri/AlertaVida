# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/CaioOlivieri/AlertaVida/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                     |    Stmts |     Miss |   Cover |   Missing |
|----------------------------------------- | -------: | -------: | ------: | --------: |
| src/alertavida/\_\_init\_\_.py           |        0 |        0 |    100% |           |
| src/alertavida/database.py               |       82 |        0 |    100% |           |
| src/alertavida/domain/\_\_init\_\_.py    |        5 |        0 |    100% |           |
| src/alertavida/domain/alerta.py          |      108 |        1 |     99% |       111 |
| src/alertavida/domain/cobrade.py         |       11 |        0 |    100% |           |
| src/alertavida/domain/coordenadas.py     |        5 |        0 |    100% |           |
| src/alertavida/domain/detector.py        |       64 |        0 |    100% |           |
| src/alertavida/domain/enums.py           |       70 |        0 |    100% |           |
| src/alertavida/domain/geographic.py      |       38 |        0 |    100% |           |
| src/alertavida/domain/municipio.py       |       18 |        0 |    100% |           |
| src/alertavida/events.py                 |       52 |        0 |    100% |           |
| src/alertavida/ingestion/\_\_init\_\_.py |        2 |        0 |    100% |           |
| src/alertavida/ingestion/orquestrador.py |       75 |        0 |    100% |           |
| src/alertavida/monitor.py                |       15 |        0 |    100% |           |
| src/alertavida/reporting.py              |       10 |        0 |    100% |           |
| src/alertavida/scheduler.py              |       40 |        0 |    100% |           |
| src/alertavida/sources/\_\_init\_\_.py   |        4 |        0 |    100% |           |
| src/alertavida/sources/\_http.py         |       48 |        0 |    100% |           |
| src/alertavida/sources/base.py           |       23 |        0 |    100% |           |
| src/alertavida/sources/cemaden.py        |       52 |        0 |    100% |           |
| src/alertavida/sources/nasa\_eonet.py    |      105 |        0 |    100% |           |
| **TOTAL**                                |  **827** |    **1** | **99%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/CaioOlivieri/AlertaVida/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/CaioOlivieri/AlertaVida/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CaioOlivieri/AlertaVida/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/CaioOlivieri/AlertaVida/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FCaioOlivieri%2FAlertaVida%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/CaioOlivieri/AlertaVida/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.