import os

import boto3
from botocore.config import Config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=os.getenv("SEAWEEDFS_S3_ENDPOINT"),
            aws_access_key_id=os.getenv("SEAWEEDFS_S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("SEAWEEDFS_S3_SECRET_KEY"),
            region_name=os.getenv("SEAWEEDFS_S3_REGION", "us-east-1"),
            # SeaweedFS não roteia por subdomínio de bucket — precisa de
            # path-style (host/bucket/key), mesmo ajuste do lado Node
            # (Agent-Api/src/infrastructure/storage/s3-client.ts).
            config=Config(s3={"addressing_style": "path"}),
        )
    return _client


def download_object(s3_key: str) -> bytes:
    """Baixa o conteúdo bruto de um documento de RAG anexado pelo Agent Console
    — a chave já vem prefixada (SEAWEEDFS_S3_PREFIX/rag-documents/...)."""
    bucket = os.getenv("SEAWEEDFS_S3_BUCKET")
    response = _get_client().get_object(Bucket=bucket, Key=s3_key)
    return response["Body"].read()
