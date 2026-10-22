from contextlib import contextmanager

from chaosgym.assertions import effect_count


@contextmanager
def fixture(context):
    def operation():
        return context.ledger.commit("work", "item", "request")

    context.register_tool("operation", operation, tracks_commits=True)
    context.python_assertions.append(
        lambda run: effect_count(run.ledger, kind="work", resource_id="item", equals=1)
    )
    try:
        yield
    finally:
        context.ledger.commit("cleanup", "fixture", "closed")


@contextmanager
def broken_setup(context):
    raise RuntimeError("private setup details")
    yield


@contextmanager
def broken_teardown(context):
    with fixture(context):
        yield
    raise RuntimeError("private teardown details")


def recover(context):
    try:
        context.tool("operation")()
    except TimeoutError:
        context.tool("operation")()


def crash(context):
    context.tool("operation")()
    raise RuntimeError("private application details")


def skip(context):
    pass


def loop(context):
    while True:
        try:
            context.tool("operation")()
        except TimeoutError:
            pass


def hang(context):
    try:
        context.tool("operation")()
    except TimeoutError:
        pass
    while True:
        pass


def exit_worker(context):
    import os

    os._exit(1)


def noisy(context):
    print("private application output")
    recover(context)


def ignore_cancellation(context):
    while True:
        try:
            while True:
                pass
        except BaseException:
            pass


def awaitable_application(context):
    async def operation():
        return 1

    return operation()


def generator_application(context):
    yield 1


@contextmanager
def broken_assertion(context):
    with fixture(context):
        context.python_assertions.append(lambda run: None)
        yield
