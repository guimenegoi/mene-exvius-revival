/* Android CPython lib-dynload asset extractor for the existing FFBE JNI probe.
 * Lab-only: checks signed asset names and lengths, not per-file SHA-256.
 * Native extensions are copied to app-private read-only files for dlopen.
 */
#include "native_assets.h"
#include <android/asset_manager.h>
#include <android/asset_manager_jni.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define MANIFEST "ffbe_python/dynload-index.txt"
#define PREFIX "ffbe_python/dynload/"
#define MAX_MANIFEST (16 * 1024)
#define MAX_NAME 160
#define MAX_MODULES 128

static int fail(char *error, size_t error_len, const char *message) {
    snprintf(error, error_len, "%s", message);
    return -1;
}

static int valid_name(const char *name) {
    size_t length = strlen(name);
    if (length < 4 || length >= MAX_NAME || name[0] == '.') return 0;
    if (strcmp(name + length - 3, ".so")) return 0;
    for (const unsigned char *p = (const unsigned char *)name; *p; ++p) {
        if ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z') ||
            (*p >= '0' && *p <= '9') || *p == '_' || *p == '-' || *p == '.') {
            continue;
        }
        return 0;
    }
    return 1;
}

static int copy_module(AAssetManager *manager, const char *name,
                       const char *directory, char *error, size_t error_len) {
    char relative[PATH_MAX], target[PATH_MAX], stage[PATH_MAX];
    if (snprintf(relative, sizeof(relative), "%s%s", PREFIX, name) >=
            (int)sizeof(relative) ||
        snprintf(target, sizeof(target), "%s/%s", directory, name) >=
            (int)sizeof(target) ||
        snprintf(stage, sizeof(stage), "%s.installing", target) >=
            (int)sizeof(stage)) {
        return fail(error, error_len, "Native module path too long");
    }
    AAsset *asset = AAssetManager_open(manager, relative, AASSET_MODE_STREAMING);
    if (!asset) return fail(error, error_len, "Native module asset missing");
    off64_t expected = AAsset_getLength64(asset);
    if (expected <= 0 || expected > 64 * 1024 * 1024) {
        AAsset_close(asset);
        return fail(error, error_len, "Invalid native module length");
    }
    struct stat old;
    if (stat(target, &old) == 0 && S_ISREG(old.st_mode) && old.st_size == expected) {
        AAsset_close(asset);
        return 0;
    }
    FILE *out = fopen(stage, "wb");
    if (!out) {
        AAsset_close(asset);
        return fail(error, error_len, "Cannot create native staging file");
    }
    unsigned char buffer[65536];
    off64_t copied = 0;
    int bytes, bad = 0;
    while ((bytes = AAsset_read(asset, buffer, sizeof(buffer))) > 0) {
        if (fwrite(buffer, 1, (size_t)bytes, out) != (size_t)bytes) {
            bad = 1;
            break;
        }
        copied += bytes;
    }
    if (bytes < 0 || copied != expected || fflush(out)) bad = 1;
    if (fchmod(fileno(out), 0400)) bad = 1;
    if (fclose(out)) bad = 1;
    AAsset_close(asset);
    if (!bad && rename(stage, target) == 0) return 0;
    unlink(stage);
    return fail(error, error_len, "Native module install failed");
}

int ffbe_prepare_dynload(JNIEnv *env, jobject context, const char *stdlib_zip,
                         char *out_dir, size_t out_len,
                         char *error, size_t error_len) {
    const char *suffix = "/stdlib.zip";
    size_t zip_len = strlen(stdlib_zip);
    if (zip_len <= strlen(suffix) ||
        strcmp(stdlib_zip + zip_len - strlen(suffix), suffix)) {
        return fail(error, error_len, "Invalid stdlib location");
    }
    if (snprintf(out_dir, out_len, "%.*s/lib-dynload",
                 (int)(zip_len - strlen(suffix)), stdlib_zip) >= (int)out_len) {
        return fail(error, error_len, "Native module directory too long");
    }
    if (mkdir(out_dir, 0700) && errno != EEXIST) {
        return fail(error, error_len, "Cannot create lib-dynload directory");
    }
    jclass cls = (*env)->GetObjectClass(env, context);
    jmethodID assets_id = (*env)->GetMethodID(env, cls, "getAssets",
                                              "()Landroid/content/res/AssetManager;");
    if (!assets_id) return fail(error, error_len, "Context getAssets missing");
    jobject assets = (*env)->CallObjectMethod(env, context, assets_id);
    if ((*env)->ExceptionCheck(env) || !assets) {
        return fail(error, error_len, "Context asset manager unavailable");
    }
    AAssetManager *manager = AAssetManager_fromJava(env, assets);
    if (!manager) return fail(error, error_len, "Invalid Android asset manager");
    AAsset *manifest = AAssetManager_open(manager, MANIFEST, AASSET_MODE_BUFFER);
    if (!manifest) return fail(error, error_len, "Native module manifest missing");
    off64_t length = AAsset_getLength64(manifest);
    if (length <= 0 || length > MAX_MANIFEST) {
        AAsset_close(manifest);
        return fail(error, error_len, "Invalid native module manifest size");
    }
    char list[MAX_MANIFEST + 1];
    int received = AAsset_read(manifest, list, (size_t)length);
    AAsset_close(manifest);
    if (received != length) return fail(error, error_len, "Cannot read native manifest");
    list[received] = '\0';
    int count = 0;
    char *start = list;
    for (char *end = list; ; ++end) {
        if (*end == '\n' || *end == '\0') {
            char delimiter = *end;
            *end = '\0';
            if (start < end) {
                if (!valid_name(start) || ++count > MAX_MODULES) {
                    return fail(error, error_len, "Invalid native module name");
                }
                if (copy_module(manager, start, out_dir, error, error_len)) return -1;
            }
            if (delimiter == '\0') break;
            start = end + 1;
        }
    }
    return count ? 0 : fail(error, error_len, "No native modules in manifest");
}
