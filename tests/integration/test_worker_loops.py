import asyncio

import pytest

from spectra.bootstrap.worker import every


@pytest.mark.anyio
async def test_a_failing_periodic_task_runs_again_instead_of_stopping_the_worker() -> None:
    stop = asyncio.Event()
    calls: list[int] = []

    async def flaky() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            raise ConnectionError("postgres went away")
        stop.set()

    async with asyncio.timeout(5.0):
        await every(0.01, flaky, stop=stop)
    assert calls == [0, 1]


@pytest.mark.anyio
async def test_a_periodic_task_stops_with_the_worker() -> None:
    stop = asyncio.Event()
    calls: list[int] = []

    async def count() -> None:
        calls.append(len(calls))

    async with asyncio.timeout(5.0), asyncio.TaskGroup() as group:
        group.create_task(every(60.0, count, stop=stop))
        await asyncio.sleep(0.05)
        stop.set()
    assert calls == [0]
