FROM alpine:latest 

WORKDIR /work_dir

COPY skript.sh .

RUN chmod +x skript.sh

RUN mkdir /data

ENTRYPOINT ["./skript.sh"]