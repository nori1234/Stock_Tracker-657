"""アラートのエッジトリガー化と時間ベースのクールダウンに使う状態の永続化。

定期実行 (cron / GitHub Actions) では、条件が成立し続けている間は毎回発火してしまう。
2 段階で重複を抑える:

  1. エッジトリガー: 「いったん成立した条件は、条件が外れて再武装するまで
     再通知しない」ためにアクティブな条件キー集合を保存する。
  2. クールダウン: 条件が短時間で成立/解消を繰り返す (フラッピング) ケースで、
     最後に通知した時刻から一定時間内は再通知しないため、通知時刻も保存する。

条件キー = "<symbol>|<type>|<value>" (銘柄×条件で一意)。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from stocks.alerts import AlertHit

# last_notified が無制限に増えないよう、この日数より古い記録は保存時に捨てる
_PRUNE_AFTER_DAYS = 30


def hit_key(hit: AlertHit) -> str:
    return f"{hit.quote.symbol}|{hit.condition.type}|{hit.condition.value}"


class AlertStateStore:
    """アクティブな条件キー集合と最終通知時刻をファイルに永続化する。"""

    def __init__(self, path: str = "./storage/stock_alert_state.json"):
        self.path = Path(path)
        self._active: Set[str] = set()
        self._last_notified: Dict[str, str] = {}   # key -> ISO8601 文字列
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._active = set(data.get("active", []))
            self._last_notified = dict(data.get("last_notified", {}))
        except (json.JSONDecodeError, OSError):
            # 壊れた状態ファイルは初期状態として扱い、握りつぶす
            self._active = set()
            self._last_notified = {}

    @property
    def active(self) -> Set[str]:
        return set(self._active)

    def filter_new(self, hits: List[AlertHit]) -> Tuple[List[AlertHit], Set[str]]:
        """発火中の hits のうち「前回アクティブで無かった」ものだけ返す。

        戻り値: (新規に通知すべき hits, 今回アクティブな全キー集合)
        """
        current_keys = {hit_key(h) for h in hits}
        new_hits = [h for h in hits if hit_key(h) not in self._active]
        return new_hits, current_keys

    def cooled_down(self, key: str, now: datetime, cooldown_minutes: int) -> bool:
        """key が最後に通知されてから cooldown_minutes 以上経っていれば True。

        cooldown_minutes<=0 なら常に True (クールダウン無効)。
        """
        if cooldown_minutes <= 0:
            return True
        ts = self._last_notified.get(key)
        if not ts:
            return True
        try:
            last = datetime.fromisoformat(ts)
        except ValueError:
            return True
        return now - last >= timedelta(minutes=cooldown_minutes)

    def commit(
        self,
        active_keys: Iterable[str],
        notified_keys: Iterable[str] = (),
        now: datetime | None = None,
    ) -> None:
        """今回アクティブなキー集合と通知時刻で状態を更新して保存する。

        前回アクティブで今回発火しなかった条件は active から消えるため、
        次に成立したときは再び新規通知される (= 再武装)。
        notified_keys には今回 LINE 送信した条件キーを渡す (通知時刻を記録)。
        """
        now = now or datetime.now()
        self._active = set(active_keys)
        for key in notified_keys:
            self._last_notified[key] = now.isoformat(timespec="seconds")
        self._prune(now)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active": sorted(self._active),
            "last_notified": dict(sorted(self._last_notified.items())),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _prune(self, now: datetime) -> None:
        """古い last_notified を捨ててファイルの肥大化を防ぐ。"""
        cutoff = now - timedelta(days=_PRUNE_AFTER_DAYS)
        kept: Dict[str, str] = {}
        for key, ts in self._last_notified.items():
            try:
                if datetime.fromisoformat(ts) >= cutoff:
                    kept[key] = ts
            except ValueError:
                continue
        self._last_notified = kept
