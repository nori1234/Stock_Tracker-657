import os

# オフライン環境でのテレメトリ送信タイムアウトを防ぐ(crewai import 前に設定)
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
