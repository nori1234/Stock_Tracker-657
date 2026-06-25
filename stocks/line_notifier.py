"""LINE Messaging API への push 送信。

LINE Notify は 2025-03-31 で終了したため、Messaging API の push エンドポイントを使う。
事前準備:
  1. LINE Developers でチャネル (Messaging API) を作成
  2. チャネルアクセストークン (長期) を発行 → LINE_CHANNEL_ACCESS_TOKEN
  3. 送信先 userId / groupId を取得 → LINE_TO
"""
from __future__ import annotations

import time
from typing import Callable, Optional

# 一時的な失敗としてリトライ対象にするステータス (レート超過 / サーバー側障害)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LineNotifyError(RuntimeError):
    """LINE への送信に失敗したとき送出。"""


class LineNotifier:
    PUSH_URL = "https://api.line.me/v2/bot/message/push"

    def __init__(self, token: str, to: str, session=None, timeout: int = 10,
                 max_retries: int = 3, backoff: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise LineNotifyError(
                "LINE チャネルアクセストークンが未設定です "
                "(stocks.yaml の line.channel_access_token か 環境変数 LINE_CHANNEL_ACCESS_TOKEN)。"
            )
        if not to:
            raise LineNotifyError(
                "LINE 送信先が未設定です "
                "(stocks.yaml の line.to か 環境変数 LINE_TO)。"
            )
        self.token = token
        self.to = to
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self._sleep = sleep
        self._session = session

    def _get_session(self):
        if self._session is not None:
            return self._session
        import requests  # 遅延 import (テストではスタブ session を注入)

        self._session = requests.Session()
        return self._session

    def push(self, text: str) -> None:
        """テキストメッセージを 1 通 push する。LINE の 1 通上限 5000 字で切り詰める。"""
        self._push_messages([{"type": "text", "text": text[:5000]}])

    def push_flex(self, alt_text: str, contents: dict) -> None:
        """Flex Message を 1 通 push する。

        alt_text は通知一覧/プレビュー用のテキスト、contents は Flex の
        bubble または carousel オブジェクト。
        """
        self._push_messages([{
            "type": "flex",
            "altText": alt_text[:400],
            "contents": contents,
        }])

    def _push_messages(self, messages: list) -> None:
        """指数バックオフでリトライしつつ push する。

        429 / 5xx と通信例外は一時的失敗としてリトライ。それ以外の 4xx
        (401 認証エラー等) は即座に失敗させる (リトライしても無駄なため)。
        """
        payload = {"to": self.to, "messages": messages}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        last_reason = ""
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._get_session().post(
                    self.PUSH_URL, json=payload, headers=headers, timeout=self.timeout
                )
            except Exception as e:  # 通信例外 (タイムアウト等) は一時的失敗とみなす
                last_reason = f"通信例外: {e}"
            else:
                if resp.status_code == 200:
                    return
                body = _safe_text(resp)
                if resp.status_code not in _RETRYABLE_STATUS:
                    raise LineNotifyError(
                        f"LINE push に失敗しました (status={resp.status_code}): {body}"
                    )
                last_reason = f"status={resp.status_code}: {body}"

            if attempt < self.max_retries:
                self._sleep(self.backoff * (2 ** attempt))

        raise LineNotifyError(
            f"LINE push に失敗しました (リトライ {self.max_retries} 回): {last_reason}"
        )


def _safe_text(resp) -> Optional[str]:
    try:
        return resp.text
    except Exception:
        return None
