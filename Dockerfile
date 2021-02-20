FROM python:2.7

MAINTAINER Li Xipeng <lixipeng@oneprocloud.com>

COPY ./requirements.txt /requirements.txt
COPY ./vegaops2n9e.py /vegaops2n9e.py
COPY ./config.yaml /config.yaml

RUN pip install -r /requirements.txt
