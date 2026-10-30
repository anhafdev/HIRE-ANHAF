from __future__ import annotations


class CryptoVerifyError(Exception):
    pass


class ConfigurationError(CryptoVerifyError):
    pass


class ProviderCallFailed(CryptoVerifyError):
    def __init__(self, provider: str, reason: str, retryable: bool = True) -> None:
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason
        self.retryable = retryable


class ProviderResponseInvalid(ProviderCallFailed):
    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(provider, f"malformed response ({reason})", retryable=False)


class ProviderBenched(ProviderCallFailed):
    def __init__(self, provider: str, seconds_left: float) -> None:
        super().__init__(provider, f"circuit open for another {seconds_left:.0f}s", retryable=False)


class ProvidersDisagree(CryptoVerifyError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NoProviderAnswered(CryptoVerifyError):
    def __init__(self, failures: list) -> None:
        super().__init__("; ".join(item.as_text() for item in failures) or "no provider available")
        self.failures = failures
