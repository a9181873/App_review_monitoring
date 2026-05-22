#!/bin/bash
# App 評論監測 — Docker 一鍵執行
# 用法：bash run.sh

cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "❌ 請先建立 .env 檔案（參考 .env.example）"
    exit 1
fi

docker compose build --quiet
docker compose run --rm app-review
