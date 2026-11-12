#ifndef FFBE_NATIVE_ASSETS_H
#define FFBE_NATIVE_ASSETS_H
#include <jni.h>
#include <stddef.h>

/* Dev-only loader. Returns 0 on success; no Python objects are touched. */
int ffbe_prepare_dynload(JNIEnv *env, jobject context, const char *stdlib_zip,
                         char *out_dir, size_t out_len,
                         char *error, size_t error_len);
#endif
