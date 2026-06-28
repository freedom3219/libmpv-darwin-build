{
  pkgs ? import ../../utils/default/pkgs.nix,
  os ? import ../../utils/default/os.nix,
  arch ? pkgs.callPackage ../../utils/default/arch.nix { },
}:

let
  name = "libplacebo";
  packageLocks = import ../../../packages.lock.nix;
  packageLock = packageLocks.${name};
  inherit (packageLock) version;

  callPackage = pkgs.lib.callPackageWith { inherit pkgs os arch; };
  nativeFile = callPackage ../../utils/native-file/default.nix { };
  crossFile = callPackage ../../utils/cross-file/default.nix { };
  fetchTarball = callPackage ../../utils/fetch-tarball/default.nix;

  nativeBuildInputs = [
    pkgs.meson
    pkgs.ninja
    pkgs.pkg-config
    pkgs.python3
  ];

  pname = import ../../utils/name/package.nix name;
  src = fetchTarball {
    name = "${pname}-source-${version}";
    inherit (packageLock) url sha256;
  };
  glad = fetchTarball {
    name = "${pname}-glad-source-${packageLocks.libplaceboGlad.version}";
    inherit (packageLocks.libplaceboGlad) url sha256;
  };
  jinja = fetchTarball {
    name = "${pname}-jinja-source-${packageLocks.libplaceboJinja.version}";
    inherit (packageLocks.libplaceboJinja) url sha256;
  };
  markupsafe = fetchTarball {
    name = "${pname}-markupsafe-source-${packageLocks.libplaceboMarkupsafe.version}";
    inherit (packageLocks.libplaceboMarkupsafe) url sha256;
  };
  fastFloat = fetchTarball {
    name = "${pname}-fast-float-source-${packageLocks.libplaceboFastFloat.version}";
    inherit (packageLocks.libplaceboFastFloat) url sha256;
  };
  vulkanHeaders = fetchTarball {
    name = "${pname}-vulkan-headers-source-${packageLocks.libplaceboVulkanHeaders.version}";
    inherit (packageLocks.libplaceboVulkanHeaders) url sha256;
  };
  sourceWithSubmodules = pkgs.runCommand "${pname}-source-with-submodules-${version}" { } ''
    cp -r ${src} src
    chmod -R 777 src

    rm -rf src/3rdparty/glad
    rm -rf src/3rdparty/jinja
    rm -rf src/3rdparty/markupsafe
    rm -rf src/3rdparty/fast_float
    rm -rf src/3rdparty/Vulkan-Headers

    cp -r ${glad} src/3rdparty/glad
    cp -r ${jinja} src/3rdparty/jinja
    cp -r ${markupsafe} src/3rdparty/markupsafe
    cp -r ${fastFloat} src/3rdparty/fast_float
    cp -r ${vulkanHeaders} src/3rdparty/Vulkan-Headers

    cp -r src $out
  '';
  patchedSource = callPackage ../../utils/patch-shebangs/default.nix {
    name = "${pname}-patched-source-${version}";
    src = sourceWithSubmodules;
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
