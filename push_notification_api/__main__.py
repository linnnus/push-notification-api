from argparse import ArgumentParser
from .app import app

def main():
    parser = ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run development server (otherwise prod is run)")
    parser.add_argument("--host", default="0.0.0.0", type=str, help="Host to run as")
    parser.add_argument("--port", default=8000, type=int, help="Port to listen on")
    parser.add_argument("--num-workers", default=3, type=int, help="Number of workers for production server")
    args = parser.parse_args()

    if args.dev:
        print("Running development server")
        from werkzeug.serving import run_simple
        run_simple(args.host, args.port, app, use_debugger=True)
    else:
        from gunicorn.app.base import BaseApplication

        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            def load_config(self):
                config = {key: value for key, value in self.options.items()
                          if key in self.cfg.settings and value is not None}
                for key, value in config.items():
                    self.cfg.set(key.lower(), value)
            def load(self):
                return self.application

        options = {
            "accesslog": "-",
            "bind": "%s:%s" % (args.host, args.port),
            "workers": args.num_workers,
        }
        StandaloneApplication(app, options).run()

    return 0

if __name__ == "__main__":
    exit(main())
