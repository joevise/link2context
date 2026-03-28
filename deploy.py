#!/usr/bin/env python3
"""
deploy.py - Deploy link2context to 67.209.190.54
Run from link2context/ directory: python3 deploy.py
"""
import paramiko, tarfile, io
from pathlib import Path

REMOTE_HOST = "67.209.190.54"
REMOTE_USER = "root"
REMOTE_PASS = "LMqdn0MZxhyl"
REMOTE_DIR = "/opt/link2context"
PROJECT_DIR = Path(__file__).parent

EXCLUDE = {'.git', '__pycache__', 'cache', '.venv', 'venv', '.env', 'deploy.py'}

def deploy():
    print(f"🚀 Deploying link2context to {REMOTE_HOST}...")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for item in PROJECT_DIR.rglob('*'):
            rel = item.relative_to(PROJECT_DIR)
            if any(part in EXCLUDE for part in rel.parts):
                continue
            if item.is_file():
                tar.add(item, arcname=str(rel))
    buf.seek(0)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(REMOTE_HOST, username=REMOTE_USER, password=REMOTE_PASS, timeout=10)
    sftp = ssh.open_sftp()

    ssh.exec_command(f"mkdir -p {REMOTE_DIR}")
    sftp.putfo(buf, "/tmp/l2c-deploy.tar.gz")

    print("🔨 Building and restarting...")
    cmd = f"""
    set -e
    rm -rf {REMOTE_DIR}/*
    cd {REMOTE_DIR}
    tar xzf /tmp/l2c-deploy.tar.gz
    rm -f /tmp/l2c-deploy.tar.gz
    docker compose down 2>/dev/null || true
    docker compose up -d --build 2>&1
    echo "=== STATUS ==="
    docker compose ps
    """
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=600)
    for line in stdout:
        print(f"  {line.strip()}")

    sftp.close()
    ssh.close()
    print(f"\n🎉 Done! http://{REMOTE_HOST}:8000")

if __name__ == "__main__":
    deploy()
