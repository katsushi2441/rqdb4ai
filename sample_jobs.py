import time


def echo_job(message: str = "hello from rqdb4ai", delay: float = 0.0) -> dict:
    if delay:
        time.sleep(delay)
    return {"message": message, "delay": delay}


def failing_job(message: str = "sample failure") -> None:
    raise RuntimeError(message)
