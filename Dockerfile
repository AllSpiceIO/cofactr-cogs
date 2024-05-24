FROM python:3.12-bookworm

COPY entrypoint.py /entrypoint.py
COPY cofactr_cogs /cofactr_cogs

RUN pip install requests

ENTRYPOINT [ "/entrypoint.py" ]
