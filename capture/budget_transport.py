"""Budget OpenEnv engine HTTP attempts before they reach the local engine."""

import asyncio
import json

import httpx

from .engine_budget import validate_engine_logps
from .relay import ROUTE


class BudgetTransport(httpx.AsyncHTTPTransport):
    def __init__(self, budget, base_url, served_model):
        super().__init__(trust_env=False, retries=0)
        self.budget = budget
        self.completion_url = httpx.URL(base_url + ROUTE)
        self.served_model = served_model
        self.lock = asyncio.Lock()

    async def handle_async_request(self, request):
        if request.method != "POST" or request.url != self.completion_url:
            return self.reject("unexpected engine route")
        # OpenCode may ask for a title while its main turn is still running.
        async with self.lock:
            return await self.forward_bounded(request)

    async def forward_bounded(self, request):
        try:
            body = self.budget.admit(json.loads(request.content))
        except ValueError as exc:
            return self.reject(str(exc))

        headers = request.headers.copy()
        del headers["content-length"]
        bounded = httpx.Request(request.method, request.url, json=body, headers=headers,
                                extensions=request.extensions)
        try:
            response = await super().handle_async_request(bounded)
            try:
                if not response.is_success:
                    raise ValueError("engine rejected completion")
                await response.aread()
                payload = response.json()
                validate_engine_logps(payload, self.served_model)
                self.budget.settle(payload)
                return response
            except (httpx.HTTPError, ValueError):
                await response.aclose()
                raise
        except (httpx.HTTPError, ValueError):
            self.budget.failed = True
            return self.reject("engine failed or returned invalid token accounting")

    @staticmethod
    def reject(message):
        # OpenEnv retries transient responses or tries to repair a parameter named in a 400.
        return httpx.Response(422, json={"error": {"message": message}})
