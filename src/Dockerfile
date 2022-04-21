FROM mambaorg/micromamba
COPY --chown=$MAMBA_USER:$MAMBA_USER env.yaml /tmp/env.yaml
RUN micromamba create -y -f /tmp/env.yaml && \
    micromamba clean --all --yes

WORKDIR /app
ADD --chown=$MAMBA_USER:$MAMBA_USER data-docker.tar /app
COPY --chown=$MAMBA_USER:$MAMBA_USER emitpy /app/emitpy
COPY --chown=$MAMBA_USER:$MAMBA_USER app.py /app
CMD micromamba -n emitpy run gunicorn app:app -b :5000
# CMD tail -f /dev/null