{
  description = "python devshell";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.2511.0";
  };

  outputs =
    {
      self,
      nixpkgs,
    }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      python3 = pkgs.python313;
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
