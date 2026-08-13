import asyncio
import os
from pathlib import Path

from bot import scanner


HOST = "0.0.0.0"
DEFAULT_PORT = 10000


async def http_handler(reader, writer):

    try:

        request = await reader.read(4096)

        if not request:
            return

        request_line = (
            request
            .decode("utf-8", errors="ignore")
            .splitlines()[0]
        )

        parts = request_line.split(" ")

        if len(parts) < 2:
            return

        path = parts[1]

        if path == "/" or path == "/index.html":

            file_path = Path("index.html")

            if not file_path.exists():

                body = b"index.html not found"

                response = (
                    b"HTTP/1.1 404 Not Found\r\n"
                    b"Content-Type: text/plain; charset=utf-8\r\n"
                    b"Content-Length: "
                    + str(len(body)).encode()
                    + b"\r\n"
                    b"Connection: close\r\n\r\n"
                    + body
                )

            else:

                body = file_path.read_bytes()

                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/html; charset=utf-8\r\n"
                    b"Content-Length: "
                    + str(len(body)).encode()
                    + b"\r\n"
                    b"Connection: close\r\n\r\n"
                    + body
                )

        else:

            body = b"OK"

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Content-Length: 2\r\n"
                b"Connection: close\r\n\r\n"
                b"OK"
            )

        writer.write(response)

        await writer.drain()

    except Exception as error:

        print(
            f"HTTP ERROR: {error}",
            flush=True
        )

    finally:

        writer.close()

        try:
            await writer.wait_closed()
        except Exception:
            pass


async def main():

    port = int(
        os.environ.get(
            "PORT",
            DEFAULT_PORT
        )
    )

    print(
        "SERVER.PY CARICATO",
        flush=True
    )

    print(
        f"Starting web server on "
        f"{HOST}:{port}",
        flush=True
    )

    server = await asyncio.start_server(
        http_handler,
        HOST,
        port
    )

    print(
        f"WEB SERVER RUNNING ON PORT {port}",
        flush=True
    )

    await asyncio.gather(
        scanner(),
        server.serve_forever()
    )


if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "SERVER STOPPED",
            flush=True
        )

    except Exception as error:

        print(
            f"FATAL SERVER ERROR: {error}",
            flush=True
        )
