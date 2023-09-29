{
  description = "push-service: generate a unique URL which can be used to send push notifications to your device.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/release-23.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        python = pkgs.python311;

        # Rebuidlments for running.
        requirements-run = (ps: with ps; [
            cryptography
            py-vapid
            pycparser
            pywebpush
            werkzeug
            waitress
        ]);
      in
      {
        packages = {
          default = python.pkgs.buildPythonApplication rec {
            pname = "push-notification-api";
            version = "0.0.0";

            src = ./.;
            format = "setuptools";

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

        nixosModules = {
        };

        devShell = pkgs.mkShell {
          nativeBuildInputs = [ (python.withPackages requirements-run) ];
        };
      }
    );
}
