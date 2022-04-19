FROM mambaorg/micromamba:0.22.0
COPY --chown=$MAMBA_USER:$MAMBA_USER env.txt /tmp/env.txt
RUN micromamba create -n emitpy -y -f /tmp/env.txt && \
    micromamba clean --all --yes

WORKDIR /app
COPY data /app/data
COPY emitpy /app/emitpy
COPY emitpy/parameters-docker.py /app/emitpy/parameters.py
COPY app.py /app
ENTRYPOINT ["micromamba", "run", "--no-capture-output", "-n", "emitpy", "python", "app.py"]