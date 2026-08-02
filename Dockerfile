FROM python:3.14-slim AS builder

WORKDIR /app

# git is needed for the `discord.py @ git+https://...` requirement,
# the rest is needed to build asyncmy's C-extension
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.14-slim

WORKDIR /app

# runtime-only dependency for asyncmy (mariadb client lib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

COPY . .

RUN chmod +x docker/entrypoint.sh

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["python", "main.py"]
