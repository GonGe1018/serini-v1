import os

os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test")
os.environ.setdefault("AES_SECRET_KEY", "00" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test")
os.environ.setdefault("ADMIN_USERNAME", "test")
os.environ.setdefault("ADMIN_PASSWORD", "test")
os.environ["ENV_FILE"] = "/dev/null"
