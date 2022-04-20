FROM mambaorg/micromamba
COPY --chown=$MAMBA_USER:$MAMBA_USER env.yaml /tmp/env.yaml
RUN micromamba create -y -f /tmp/env.yaml && \
    micromamba clean --all --yes

WORKDIR /app
COPY data /app/data
COPY emitpy /app/emitpy
COPY emitpy/parameters-docker.py /app/emitpy/parameters.py
COPY app.py /app
ENTRYPOINT ["/usr/local/bin/_entrypoint.sh", "micromamba", "run", "-n", "emitpy", "python", "app.py"]
