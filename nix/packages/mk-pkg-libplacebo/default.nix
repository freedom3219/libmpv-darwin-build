{
  pkgs ? import ../../utils/default/pkgs.nix,
  os ? import ../../utils/default/os.nix,
  arch ? pkgs.callPackage ../../utils/default/arch.nix { },
}:

let
  name = "libplacebo";
  packageLock = (import ../../../packages.lock.nix).${name};
  inherit (packageLock) version;

  callPackage = pkgs.lib.callPackageWith { inherit pkgs os arch; };
  nativeFile = callPackage ../../utils/native-file/default.nix { };
  crossFile = callPackage ../../utils/cross-file/default.nix { };

  nativeBuildInputs = [
    pkgs.meson
    pkgs.ninja
    pkgs.pkg-config
    pkgs.python3
  ];

  pname = import ../../utils/name/package.nix name;
  src = callPackage ../../utils/fetch-tarball/default.nix {
    name = "${pname}-source-${version}";
    inherit (packageLock) url sha256;
  };
  patchedSource = callPackage ../../utils/patch-shebangs/default.nix {
    name = "${pname}-patched-source-${version}";
    inherit src;
    inherit nativeBuildInputs;
  };
in

pkgs.stdenvNoCC.mkDerivation {
  name = "${pname}-${os}-${arch}-${version}";
  pname = pname;
  inherit version;
  src = patchedSource;
  dontUnpack = true;
  enableParallelBuilding = true;
  inherit nativeBuildInputs;
  configurePhase = ''
    meson setup build $src \
      --native-file ${nativeFile} \
      --cross-file ${crossFile} \
      --prefix=$out \
      -Ddefault_library=shared \
      -Dvulkan=disabled \
      -Dvk-proc-addr=disabled \
      -Dopengl=enabled \
      -Dgl-proc-addr=auto \
      -Dd3d11=disabled \
      -Dglslang=disabled \
      -Dshaderc=disabled \
      -Dlcms=disabled \
      -Ddovi=disabled \
      -Dlibdovi=disabled \
      -Ddemos=false \
      -Dtests=false \
      -Dbench=false \
      -Dfuzz=false \
      -Dunwind=disabled \
      -Dxxhash=disabled
  '';
  buildPhase = ''
    meson compile -vC build
  '';
  installPhase = ''
    meson install -C build
  '';
}
