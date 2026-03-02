{
  description = "python devshell";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.2311.0";
  };

  outputs =
    {
      self,
      nixpkgs,
    }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        overlays = [
          (final: prev: {
            python39 = prev.python39.override {
              packageOverrides = pyFinal: pyPrev:
                builtins.mapAttrs
                  (name: pkg:
                    if builtins.isAttrs pkg && pkg ? overridePythonAttrs
                    then pkg.overridePythonAttrs { doCheck = false; }
                    else pkg
                  )
                  pyPrev;
            };
          })
        ];
      };
      python3 = pkgs.python39;
      pythonWithPackages = python3.withPackages (
        ps: with ps; [
          black
          requests
          ansible-core
        ]
      );
      python_env = [ pythonWithPackages ];
    in
    {
      devShells.x86_64-linux.default = pkgs.mkShell {
        buildInputs = python_env;
        shellHook = ''
          export PYTHONPATH=${pythonWithPackages}/${pythonWithPackages.sitePackages};
        '';
      };
    };
}
