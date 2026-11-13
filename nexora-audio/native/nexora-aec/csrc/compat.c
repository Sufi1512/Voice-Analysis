/* glibc >= 2.38 headers redirect sscanf to __isoc23_sscanf (C23 rules: also accepts 0b
 * binary literals). WebRTC's use (parsing field-trial and config strings) needs only the
 * C99 behaviour, so define the symbol here on top of vsscanf, compiled as plain C11 (no
 * _GNU_SOURCE), which binds to the long-standing __isoc99_vsscanf. The library then loads
 * on glibc 2.35+ (Ubuntu 22.04, Debian 12) instead of requiring 2.38. */
#include <stdarg.h>
#include <stdio.h>

int __isoc23_sscanf(const char *s, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int r = vsscanf(s, fmt, ap);
    va_end(ap);
    return r;
}
