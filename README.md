# File Compressor

A small, local file-compression app with a desktop window and a browser-based interface. It uses Python's built-in `gzip` module and requires no third-party packages.

## Features

- Compress any file type into a standard `.gz` file.
- Decompress gzip (`.gz`) files.
- Choose the output location before processing.
- Process files in chunks, so the app does not need to load the whole file into memory.
- Use the native desktop window or the simple local web page.
- Keep processing on your computer; the web server listens only on `127.0.0.1`.

## Requirements

- Python 3.10 or later.
- Tkinter for the desktop window. It is included with many Python installations; on some Linux distributions it must be installed separately.

No `pip install` step is required.

## Run the app

Open a terminal in this project folder and run:

```powershell
python app.py
```

The desktop window opens. To compress or decompress a file:

1. Select the appropriate button.
2. Choose the source file.
3. Choose where to save the result. The suggested name can be changed.

The app suggests adding `.gz` when compressing. When decompressing a `.gz` file, it suggests the original name without the `.gz` extension. For other input names, it appends `.decompressed`.

Close the desktop window to stop the app and its local web server.

## Browser interface

While the app is running, open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Select a file to compress or decompress, then use the corresponding button; the result downloads through your browser.

The browser interface uses the same local server started by `app.py`. It is not a public upload service, and files are not sent to another computer.

## Compression format

Compressed files use the standard gzip format (`.gz`), which uses DEFLATE compression. Gzip works with arbitrary file contents, but it is a single-file format and may not reduce the size of files that are already compressed (such as JPEG images, videos, and many archives).

## Troubleshooting

- **The desktop window does not open:** Make sure your Python installation includes Tkinter. On Linux, install the Tkinter package provided by your distribution.
- **Port 8000 is already in use:** Stop the other program using that port, then run `python app.py` again.
- **A file cannot be decompressed:** Check that it is a valid, complete gzip file.

## Project files

- `app.py` — desktop interface, local HTTP server, and compression/decompression logic.
- `index.html` — browser interface served by the local app.
