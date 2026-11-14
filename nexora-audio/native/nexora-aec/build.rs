fn main() {
    // glibc compatibility shim (see csrc/compat.c); only Linux needs it
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux") {
        cc::Build::new().file("csrc/compat.c").flag("-std=c11").compile("nexora_compat");
    }
    println!("cargo:rerun-if-changed=csrc/compat.c");
}
