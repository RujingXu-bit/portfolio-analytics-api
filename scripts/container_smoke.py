import subprocess
import sys
import time
from uuid import UUID, uuid4

import httpx

_JWT_SECRET = "container-smoke-only-jwt-secret-key-32-characters"


def _run(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=check,
        capture_output=True,
        text=True,
    )


def published_port(output: str) -> int:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != 1 or ":" not in lines[0]:
        raise ValueError("Docker returned an unexpected published-port value")
    port = int(lines[0].rsplit(":", 1)[1])
    if not 0 < port <= 65535:
        raise ValueError("Docker returned an invalid published port")
    return port


def smoke_image(image_name: str) -> None:
    configured_user = _run(
        "docker",
        "image",
        "inspect",
        "--format",
        "{{.Config.User}}",
        image_name,
    ).stdout.strip()
    if configured_user != "10001":
        raise RuntimeError("runtime image is not configured for UID 10001")

    container_name = f"portfolio-analytics-smoke-{uuid4().hex}"
    _run(
        "docker",
        "run",
        "--detach",
        "--rm",
        "--name",
        container_name,
        "--publish",
        "127.0.0.1::8000",
        "--env",
        f"JWT_SECRET_KEY={_JWT_SECRET}",
        image_name,
    )
    try:
        port_output = _run("docker", "port", container_name, "8000/tcp").stdout
        port = published_port(port_output)
        deadline = time.monotonic() + 30
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if _run("docker", "inspect", container_name, check=False).returncode != 0:
                raise RuntimeError("application container exited before health check")
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
            except httpx.HTTPError as error:
                last_error = error
                time.sleep(0.25)
                continue
            if response.status_code == 200 and response.json() == {"status": "ok"}:
                UUID(response.headers["X-Request-ID"])
                return
            last_error = RuntimeError(
                f"unexpected health response {response.status_code}: {response.text}"
            )
            time.sleep(0.25)
        logs = _run("docker", "logs", container_name, check=False).stdout
        raise RuntimeError(f"container health check timed out: {last_error}\n{logs}")
    finally:
        _run("docker", "stop", "--time", "2", container_name, check=False)


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit("usage: python -m scripts.container_smoke IMAGE_NAME")
    smoke_image(sys.argv[1])
    print(f"Container health smoke passed for {sys.argv[1]}")


if __name__ == "__main__":
    main()
