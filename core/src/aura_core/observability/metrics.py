from threading import Lock


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests_total = 0
        self._requests_success_total = 0
        self._requests_failure_total = 0
        self._latency_ms_total = 0.0

    def record(
        self,
        status_code: int,
        latency_ms: float,
    ) -> None:
        with self._lock:
            self._requests_total += 1
            self._latency_ms_total += latency_ms

            if status_code < 400:
                self._requests_success_total += 1
            else:
                self._requests_failure_total += 1

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            latency_ms_average = (
                self._latency_ms_total / self._requests_total
                if self._requests_total
                else 0.0
            )

            return {
                "requests_total": self._requests_total,
                "requests_success_total": self._requests_success_total,
                "requests_failure_total": self._requests_failure_total,
                "latency_ms_total": round(self._latency_ms_total, 3),
                "latency_ms_average": round(latency_ms_average, 3),
            }
