FROM mcr.microsoft.com/playwright/python@sha256:3eb610b2fa7741aea0679a251150e63bd6cf1a31b9fcd94df7498945e734b493
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-deps --require-hashes -r /tmp/requirements.txt && rm /tmp/requirements.txt
