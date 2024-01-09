{
  description = "Flashing tool for JMicron JMS567";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      debug = true;
      imports = [];
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      perSystem = { self', config, pkgs, system, ... }: {
        packages.default =
          let
            py3sg = pkgs.python3.pkgs.buildPythonPackage {
              pname = "py3sg";
              version = "";
              src = pkgs.fetchFromGitHub {
                owner = "tvladyslav";
                repo = "py3_sg";
                rev = "524492b11a6218841cc2d4fe8246bbf1e5674392";
                sha256 = "sha256-wISc8OmycAJmRmqeLXP4zba210BoHTrlrIf6VdLswtE=";
              };
            };
            python = pkgs.python3.withPackages (p: [
              p.pyusb
              py3sg
            ]);
            jms567ctl_py = builtins.path {
              name = "jms567ctl.py";
              path = ./jms567ctl.py;
            };
          in
          pkgs.writeShellScriptBin "jms567ctl.sh" ''
            ${python}/bin/python3 ${jms567ctl_py} "$@"
          '';
      };
    };
}
