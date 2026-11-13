fn main() {
    cc::Build::new().file("csrc/compat.c").flag("-std=c11").compile("nexora_compat");
    println!("cargo:rerun-if-changed=csrc/compat.c");
}
