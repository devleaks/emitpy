#!/bin/sh
# Dockerfile
# WORKDIR /app/src
# CMD /app/emitpy.sh
micromamba -n emitpy run python emitpy/loadapp.py
exec micromamba -n emitpy run uvicorn --host 0.0.0.0 --port 8000 api:app