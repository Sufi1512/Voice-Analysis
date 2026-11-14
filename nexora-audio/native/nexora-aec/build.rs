fn main() {
    // glibc compatibility shim (see csrc/compat.c); only Linux needs it
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux") {
        // whole-archive: otherwise the linker may resolve the symbols from glibc before it
        // reaches this archive (seen on aarch64), and the library needs glibc 2.38 again
        cc::Build::new()
            .file("csrc/compat.c")
            .flag("-std=c11")
            .link_lib_modifier("+whole-archive")
            .compile("nexora_compat");
    }
    println!("cargo:rerun-if-changed=csrc/compat.c");
}
