import asyncio
import os
from pathlib import Path

from bot import scanner


async def http_handler(reader, writer):
    try:
        request = await reader.read(4096)

        if not request:
            return

        request_line = request.decode(
            "utf-8",
            errors="ignore"
        ).splitlines()[0]

        parts = request_line.split(" ")

        if len(parts) < 2:
            return

        path = parts[1]

        if path == "/" or path == "/index.html":

            file_path = Path("index.html")

            if file_path.exists():

                body = file_path.read_bytes()

                headers = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/html; charset=utf-8\r\n"
                    b"Content-Length: "
                    + str(len(body)).encode()
                    + b"\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )

                writer.write(
                    headers + body
                )

                await writer.drain()

            else:

                body = b"index.html not found"

                response = (
                    b"HTTP/1.1 404 Not Found\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"Content-Length: "
                    + str(len(body)).encode()
                    + b"\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                    + body
                )

                writer.write(response)

                await writer.drain()

        else:

            body = b"OK"

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 2\r\n"
                b"Connection: close\r\n"
                b"\r\n"
                b"OK"
            )

            writer.write(response)

            await writer.drain()

    except Exception as error:

        print(
            f"HTTP error: {error}",
            flush=True
        )

    finally:

        writer.close()

        try:
            await writer.wait_closed()
        except Exception:
            pass


async def main():

    print(
        "DEBUG: MAIN AVVIATO",
        flush=True
    )

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    print(
        f"DEBUG: PORT = {port}",
        flush=True
    )

    server = await asyncio.start_server(
        http_handler,
        "0.0.0.0",
        port
    )

    print(
        f"🌐 Web server running on port {port}",
        flush=True
    )

    print(
        "DEBUG: AVVIO SCANNER...",
        flush=True
    )

    await asyncio.gather(
        scanner(),
        server.serve_forever()
    )


if __name__ == "__main__":

    print(
        "DEBUG: SERVER.PY CARICATO",
        flush=True
    )

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "🛑 Server stopped",
            flush=True
        )

    except Exception as error:

        print(
            f"🔥 FATAL SERVER ERROR: {error}",
            flush=True
        )
