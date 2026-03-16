{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312.withPackages (ps: with ps; [
    requests
    django
    djangorestframework
    waybackpy
    mwparserfromhell
    beautifulsoup4
    python-dotenv
    requests-mock
    coverage
  ]);
in
pkgs.mkShell {
  packages = [
    python
  ];
}
