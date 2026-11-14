/* Minimal stand-in for Opus's os_support.h, which RNNoise v0.2's NEON and generic code
 * (src/vec.h, src/vec_neon.h) include but which neither the v0.2 tag nor its release
 * archive ships. Only x86 builds (the AVX/SSE path) build without it. Written for
 * nexora-audio, BSD-3-Clause; build_native.sh copies it into src/ when it is missing. */
#ifndef NEXORA_RNNOISE_OS_SUPPORT_H
#define NEXORA_RNNOISE_OS_SUPPORT_H

#include <string.h>

#ifndef OPUS_INLINE
#define OPUS_INLINE inline
#endif
#ifndef OPUS_CLEAR
#define OPUS_CLEAR(dst, n) (memset((dst), 0, (n) * sizeof(*(dst))))
#endif
#ifndef OPUS_COPY
#define OPUS_COPY(dst, src, n) (memcpy((dst), (src), (n) * sizeof(*(dst))))
#endif
#ifndef OPUS_MOVE
#define OPUS_MOVE(dst, src, n) (memmove((dst), (src), (n) * sizeof(*(dst))))
#endif

#endif
