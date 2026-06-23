"""アラートのエッジトリガー化に使う状態の永続化。

定期実行 (cron 等) では、条件が成立し続けている間は毎回発火してしまう。
「いったん成立した条件は、条件が外れて再武装するまで再通知しない」ために、
現在アクティブな条件キーの集合を JSON で保存する。

条件キー = "<symbol>|<type>|<value>" (銘柄×条件で一意)。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Set, Tuple

from stocks.alerts import AlertHit


def hit_key(hit: AlertHit) -> str:
    return f"{hit.quote.symbol}|{hit.condition.type}|{hit.condition.value}"


class AlertStateStore:
    """アクティブな条件キーの集合をファイルに永続化する。"""

    def __init__(self, path: str = "./storage/stock_alert_state.json"):
        self.path = Path(path)
        self._active: Set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._active = set(data.get("active", []))
        except (json.JSONDecodeError, OSError):
            # 壊れた状態ファイルは「アクティブ無し」として扱い、握りつぶす
            self._active = set()

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

    def commit(self, active_keys: Iterable[str]) -> None:
        """今回アクティブなキー集合で状態を置き換えて保存する。

        前回アクティブで今回発火しなかった条件は集合から消えるため、
        次に成立したときは再び新規通知される (= 再武装)。
        """
        self._active = set(active_keys)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"active": sorted(self._active)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
