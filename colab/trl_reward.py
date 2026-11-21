# Copyright 2020-2026 The HuggingFace Team. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# Adapted from TRL examples/async_grpo_harbor/async_grpo_harbor.py at
# b2686bf5c300756cdf878b84f83a48f794e2fb94. The budget is now an argument.

"""Clipped tool efficiency used by the Harbor reward."""


def tool_efficiency(n_tool_calls: int | None, tool_budget: float) -> float | None:
    """Measure saved tool calls on a zero-to-one scale when the count is known."""
    if n_tool_calls is None or tool_budget <= 0:
        return None
    return max(0.0, min(1.0, 1.0 - n_tool_calls / tool_budget))
