import asyncio
import os
import traceback
from pathlib import Path

print("=== SERVER.PY CARICATO ===", flush=True)

try:
    from bot import scanner
    print("=== BOT.PY IMPORTATO OK ===", flush=True)
except Exception:
    print("=== ERRORE IMPORT BOT.PY ===", flush=True)
    traceback.print_exc()
    raise


async def http_handler(reader, writer):
    try:
        request = await reader.read(4096)

        if not request:
            return

        request_line = request.decode(
            "utf-8",
            errors="ignore"
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
                body = b"index.html not found"

                response = (
                    b"HTTP/1.1 404 Not Found\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"Content-Length: "
                    + str(len(body)).encode()
                    + b"\r\n"
                    b"Connection: close\r\n\r\n"
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
                b"Connection: close\r\n\r\n"
                b"OK"
            )

            writer.write(response)
            await writer.drain()

    except Exception:
        print("=== HTTP ERROR ===", flush=True)
        traceback.print_exc()

    finally:
        writer.close()
        await writer.wait_closed()


async def run_scanner():
    print("=== AVVIO SCANNER ===", flush=True)

    try:
        await scanner()
    except Exception:
        print("=== SCANNER ERROR ===", flush=True)
        traceback.print_exc()
        raise


async def main():
    port = int(os.environ.get("PORT", "10000"))

    print(f"=== PORTA: {port} ===", flush=True)

    server = await asyncio.start_server(
        http_handler,
        "0.0.0.0",
        port
    )

    print(
        f"=== WEB SERVER AVVIATO SULLA PORTA {port} ===",
        flush=True
    )

    scanner_task = asyncio.create_task(run_scanner())

    print("=== SCANNER TASK CREATO ===", flush=True)

    try:
        await server.serve_forever()
    finally:
        scanner_task.cancel()


if __name__ == "__main__":
    print("=== AVVIO MAIN ===", flush=True)

    try:
        asyncio.run(main())
    except Exception:
        print("=== ERRORE FATALE SERVER ===", flush=True)
        traceback.print_exc()
        raise
