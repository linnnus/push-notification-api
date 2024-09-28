{
  description = "push-service: generate a unique URL which can be used to send push notifications to your device.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/release-23.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};

        python = pkgs.python311;

        # Rebuidlments for running.
        requirements-run = ps:
          with ps; [
            cryptography
            py-vapid
            pycparser
            pywebpush
            werkzeug
            gunicorn
          ];
      in {
        packages = {
          default = python.pkgs.buildPythonApplication rec {
            pname = "push-notification-api";
            version = "0.0.0";

            src = ./.;
            format = "setuptools";
            doCheck = false;

            propagatedBuildInputs = requirements-run python.pkgs;

            # Generate a setup.py for the project.
            preBuild = ''
              cat > setup.py << EOF
              from setuptools import setup

              with open('requirements.txt') as f:
                  install_requires = f.read().splitlines()

              setup(
                name='push_notification_api',
                packages=['push_notification_api'],
                package_data={'push_notification_api': ['public/*']},
                version="${version}",
                install_requires=install_requires,
                entry_points={ 'console_scripts': ['push-notification-api = push_notification_api.__main__:main'] }
              )
              EOF
            '';
          };
        };

        formatter = pkgs.writeShellScriptBin "format.sh" ''
          # Format Nix files
          ${pkgs.alejandra}/bin/alejandra --quiet -- "$@"

          # Format JavaScript files
          ${pkgs.deno}/bin/deno fmt --use-tabs=true --indent-width=8 --single-quote=false --quiet -- "$@"

          # Format Python files
          ${pkgs.black}/bin/black --quiet -- "$@"
        '';

        devShells.default = pkgs.mkShell {
          nativeBuildInputs = [(python.withPackages requirements-run)];
        };
      }
    )
    // {
      nixosModules.default = {
        pkgs,
        lib,
        config,
        ...
      }: let
        inherit (lib) mkEnableOption mkOption mkIf types;
        cfg = config.services.push-notification-api;
      in {
        options.services.push-notification-api = {
          enable = mkEnableOption "Push notification API";

            package = mkOption {
              description = "What package to use.";
              default = self.packages.${pkgs.system}.default;
              type = types.package;
            };

            socket-path = mkOption {
              description = "Path to socket where the server will listen.";
              type = types.str;
              default = "/run/push-notification-api.sock";
            };

            socket-owner = mkOption {
              description = "Owner of socket at `socket-path`. Change this if you are not using NGINX as the reverse proxy.";
              type = types.str;
              default = "nginx"; # TODO: Don't hardcode this value.
            };
          };

        config = mkIf cfg.enable {
          # Create a user to run the server under.
          users.users.push-notification-api = {
            description = "Runs push notification API service";
            group = "push-notification-api";
            isSystemUser = true;
            home = "/srv/push-notification-api";
            createHome = true;
          };
          users.groups.push-notification-api = {};

          # Create a service which runs the server.
          systemd.services.push-notification-api = {
            description = "Push notification API server";

            wantedBy = ["multi-user.target"];
            after = ["network.target"];

            serviceConfig = {
              Type = "notify";
              User = config.users.users.push-notification-api.name;
              Group = config.users.users.push-notification-api.group;
              WorkingDirectory = config.users.users.push-notification-api.home;
              ExecStart = ''
                "${cfg.package}"/bin/push-notification-api
              '';

              # Harden service
              NoNewPrivileges = "yes";
              PrivateTmp = "yes";
              PrivateDevices = "yes";
              DevicePolicy = "closed";
              ProtectControlGroups = "yes";
              ProtectKernelModules = "yes";
              ProtectKernelTunables = "yes";
              RestrictAddressFamilies = "AF_UNIX AF_INET AF_INET6 AF_NETLINK";
              RestrictNamespaces = "yes";
              RestrictRealtime = "yes";
              RestrictSUIDSGID = "yes";
              MemoryDenyWriteExecute = "yes";
              LockPersonality = "yes";
            };
          };

          # Create a socket which the server will listen on
          systemd.sockets.push-notification-api = {
            description = "Socket where the service of the same name answers HTTP requests.";

            after = [ "network.target" ];
            wantedBy = ["multi-user.target"];

            socketConfig = {
              ListenStream = cfg.socket-path;
              SocketUser = cfg.socket-owner;
              SocketMode = "600";
            };
          };
        };
      };
    };
}
