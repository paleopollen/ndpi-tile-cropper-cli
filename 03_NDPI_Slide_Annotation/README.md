
## Docker Instructions

### Build Docker Image

```shell
docker build -f Dockerfile -t ndpi-slide .
```

### Run Docker Container

```shell
docker run -p 8888:8888 -v "$PWD"/:/home/jovyan/work -t -i --rm ndpi-slide
```