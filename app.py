from __future__ import annotations

import gzip
import os
import re
import tempfile
import threading
import unicodedata
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, parse_qs, urlsplit


HOST = "127.0.0.1"
PORT = 8000
CHUNK_SIZE = 64 * 1024


def safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127).strip()
    return name if name and name not in {".", ".."} else "download"


def suggested_output_path(source_path: str, operation: str) -> str:
    source = Path(source_path)
    if operation == "compress":
        return str(source.with_name(source.name + ".gz"))
    if source.suffix.lower() == ".gz":
        return str(source.with_suffix(""))
    return str(source.with_name(source.name + ".decompressed"))


def process_local_file(source_path: str, output_path: str, operation: str) -> None:
    output = Path(output_path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
        ) as result:
            temporary_path = result.name
            if operation == "compress":
                with open(source_path, "rb") as source:
                    with gzip.GzipFile(
                        fileobj=result, mode="wb", filename="", mtime=0
                    ) as compressor:
                        FileCompressorHandler._copy(source, compressor)
            elif operation == "decompress":
                with gzip.open(source_path, "rb") as source:
                    FileCompressorHandler._copy(source, result)
            else:
                raise ValueError(f"Unknown operation: {operation}")
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
        raise


class FileCompressorHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return

        page = Path(__file__).with_name("index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in {"/compress", "/decompress"}:
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", ""))
            if content_length < 0:
                raise ValueError
        except ValueError:
            self._send_text(411, "A valid Content-Length header is required.")
            return

        query = parse_qs(urlsplit(self.path).query)
        original_name = safe_filename(query.get("filename", ["upload"])[0])

        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as source:
            remaining = content_length
            while remaining:
                chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    self._send_text(400, "The uploaded file ended unexpectedly.")
                    return
                source.write(chunk)
                remaining -= len(chunk)
            source.seek(0)

            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as result:
                try:
                    if path == "/compress":
                        with gzip.GzipFile(
                            fileobj=result, mode="wb", filename="", mtime=0
                        ) as compressor:
                            self._copy(source, compressor)
                        output_name = original_name + ".gz"
                    else:
                        with gzip.GzipFile(fileobj=source, mode="rb") as decompressor:
                            self._copy(decompressor, result)
                        output_name = (
                            original_name[:-3]
                            if original_name.lower().endswith(".gz")
                            else original_name + ".decompressed"
                        )
                except (gzip.BadGzipFile, EOFError, OSError, zlib.error) as error:
                    self._send_text(400, f"Could not process this file: {error}")
                    return

                result.seek(0, 2)
                result_size = result.tell()
                result.seek(0)
                self._send_file(result, result_size, safe_filename(output_name))

    @staticmethod
    def _copy(source, destination) -> None:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            destination.write(chunk)

    def _send_file(self, file, size: int, filename: str) -> None:
        fallback = re.sub(r"[^ -~]", "_", filename).replace('"', "_").replace("\\", "_")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename)}',
        )
        self.send_header("Content-Length", str(size))
        self.end_headers()
        while True:
            chunk = file.read(CHUNK_SIZE)
            if not chunk:
                break
            self.wfile.write(chunk)

    def _send_text(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def launch_desktop_window(server: ThreadingHTTPServer) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("File Compressor")
    root.geometry("440x280")
    root.minsize(380, 250)

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="File Compressor", font=("TkDefaultFont", 16, "bold")).pack(
        anchor="w"
    )
    ttk.Label(
        frame,
        text="Compress any file to gzip, or restore a .gz file.",
        wraplength=380,
    ).pack(anchor="w", pady=(8, 20))
    status = tk.StringVar(value="Choose an action to get started.")
    ttk.Label(frame, textvariable=status, wraplength=380).pack(
        anchor="w", pady=(20, 0)
    )

    buttons = []
    is_busy = False

    def choose_and_process(operation: str) -> None:
        nonlocal is_busy

        if operation == "compress":
            source_path = filedialog.askopenfilename(
                title="Choose a file to compress"
            )
        else:
            source_path = filedialog.askopenfilename(
                title="Choose a gzip file to decompress",
                filetypes=[("Gzip files", "*.gz"), ("All files", "*.*")],
            )
        if not source_path:
            return

        output_path = filedialog.asksaveasfilename(
            title="Save processed file",
            initialdir=str(Path(source_path).parent),
            initialfile=Path(suggested_output_path(source_path, operation)).name,
        )
        if not output_path:
            return

        for button in buttons:
            button.configure(state="disabled")
        is_busy = True
        status.set(
            "Compressing file..."
            if operation == "compress"
            else "Decompressing file..."
        )

        def finish(error: Exception | None) -> None:
            nonlocal is_busy

            is_busy = False
            for button in buttons:
                button.configure(state="normal")
            if error is not None:
                status.set("Could not process the file.")
                messagebox.showerror("File processing failed", str(error), parent=root)
                return
            status.set(f"Saved: {output_path}")

        def worker() -> None:
            try:
                process_local_file(source_path, output_path, operation)
            except Exception as error:
                root.after(0, lambda error=error: finish(error))
            else:
                root.after(0, lambda: finish(None))

        threading.Thread(target=worker, daemon=True).start()

    compress_button = ttk.Button(
        frame,
        text="Choose file to compress...",
        command=lambda: choose_and_process("compress"),
    )
    decompress_button = ttk.Button(
        frame,
        text="Choose .gz file to decompress...",
        command=lambda: choose_and_process("decompress"),
    )
    buttons.extend((compress_button, decompress_button))
    compress_button.pack(fill="x", pady=4)
    decompress_button.pack(fill="x", pady=4)

    def close_window() -> None:
        if is_busy:
            messagebox.showwarning(
                "File processing in progress",
                "Wait for the current file to finish processing before closing.",
                parent=root,
            )
            return
        server.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.mainloop()


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), FileCompressorHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    try:
        server_thread.start()
        print(f"File compressor running at http://{HOST}:{PORT}")
        launch_desktop_window(server)
    except KeyboardInterrupt:
        print("\nStopping file compressor.")
    finally:
        if server_thread.is_alive():
            server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
