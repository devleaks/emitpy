FROM python:3.10-alpine
RUN mkdir /app
WORKDIR /app
ADD requirements.txt /app
COPY emitpy /app
COPY app.py /app
COPY ../data /data
RUN pip3 install -r requirements.txt
CMD ["gunicorn", "-w 4", "-b", "0.0.0.0:8000", "main:app"]