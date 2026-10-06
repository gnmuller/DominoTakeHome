FROM public.ecr.aws/docker/library/python:3.12-slim
RUN pip install --no-cache-dir openpyxl streamlit
