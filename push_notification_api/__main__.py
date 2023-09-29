from argparse import ArgumentParser
from .app import app

def main():
    parser = ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run development server (otherwise prod is run)")
    parser.add_argument("--host", default="0.0.0.0", type=str, help="Host to run as")
    parser.add_argument("--port", default=8000, type=int, help="Port to listen on")
    args = parser.parse_args()

    if args.dev:
        print("Running development server")
        from werkzeug.serving import run_simple
        run_simple(args.host, args.port, app, use_debugger=True, use_reloader=True)
    else:
        print("Running production server")
        from waitress import serve
        serve(app, host=args.host, port=args.port)

    return 0

if __name__ == "__main__":
    exit(main())
