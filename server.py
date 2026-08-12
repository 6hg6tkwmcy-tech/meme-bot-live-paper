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
            "utf-8", errors="ignore"
        ).splitlines()[0]

        path = request_line.split(" ")[1]

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
                    b"Connection: close\r\n\r\n"
                )

                writer.write(headers + body)
                await writer.drain()

        else:
            body = b"OK"

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 2\r\n"
                b"Connection: close\r\n\r\n"
                b"OK"
            )

            writer.write(response)
            await writer.drain()

    except Exception as error:
        print(f"HTTP error: {error}")

    finally:
        writer.close()
        await writer.wait_closed()


async def main():
    port = int(os.environ.get("PORT", "10000"))

    server = await asyncio.start_server(
        http_handler,
        "0.0.0.0",
        port
    )

    print(f"🌐 Web server running on port {port}")

    await asyncio.gather(
        scanner(),
        server.serve_forever()
    )


if __name__ == "__main__":
    asyncio.run(main())
