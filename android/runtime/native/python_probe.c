/* Development-only JNI probes for the verified CPython 3.14 Android runtime.
 * No game engine, server, or save is touched. Not a production lifecycle.
 */
#include <jni.h>
#include <Python.h>
#include "native_assets.h"
#include <android/asset_manager.h>
#include <android/asset_manager_jni.h>
#include <android/log.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define TAG "FFBE-EmbeddedPython"
#define ASSET "ffbe_python/stdlib.zip"

JNIEXPORT jstring JNICALL
Java_com_mene_exvius_LocalPythonProbe_version(JNIEnv *env, jclass unused) {
    (void)unused;
    return (*env)->NewStringUTF(env, Py_GetVersion());
}

static const char *prepare_stdlib(JNIEnv *env, jobject context,
                                  char *zip_path, size_t length) {
    jclass cls = (*env)->GetObjectClass(env, context);
    jmethodID files_id = (*env)->GetMethodID(env, cls, "getFilesDir", "()Ljava/io/File;");
    jmethodID assets_id = (*env)->GetMethodID(env, cls, "getAssets",
                                              "()Landroid/content/res/AssetManager;");
    if (!files_id || !assets_id) return "Context methods unavailable";
    jobject dir = (*env)->CallObjectMethod(env, context, files_id);
    jobject assets = (*env)->CallObjectMethod(env, context, assets_id);
    if ((*env)->ExceptionCheck(env) || !dir || !assets) return "Context unavailable";
    jclass file_cls = (*env)->GetObjectClass(env, dir);
    jmethodID absolute_id = (*env)->GetMethodID(env, file_cls, "getAbsolutePath",
                                                 "()Ljava/lang/String;");
    if (!absolute_id) return "File method unavailable";
    jstring dir_str = (*env)->CallObjectMethod(env, dir, absolute_id);
    if (!dir_str || (*env)->ExceptionCheck(env)) return "getFilesDir failed";
    const char *dir_path = (*env)->GetStringUTFChars(env, dir_str, NULL);
    if (!dir_path) return "Cannot read private file path";

    char folder[PATH_MAX];
    int r1 = snprintf(folder, sizeof(folder), "%s/ffbe_python", dir_path);
    int r2 = snprintf(zip_path, length, "%s/stdlib.zip", folder);
    (*env)->ReleaseStringUTFChars(env, dir_str, dir_path);
    if (r1 < 0 || (size_t)r1 >= sizeof(folder) ||
        r2 < 0 || (size_t)r2 >= length) return "Private path too long";
    if (mkdir(folder, 0700) && errno != EEXIST) return "Cannot create Python data dir";

    AAssetManager *mgr = AAssetManager_fromJava(env, assets);
    if (!mgr) return "AssetManager unavailable";
    AAsset *asset = AAssetManager_open(mgr, ASSET, AASSET_MODE_STREAMING);
    if (!asset) return "Python stdlib asset missing";
    off64_t expected = AAsset_getLength64(asset);
    struct stat st;
    if (stat(zip_path, &st) == 0 && st.st_size == expected && expected > 0) {
        AAsset_close(asset);
        return NULL;
    }

    char staging[PATH_MAX];
    if (snprintf(staging, sizeof(staging), "%s.installing", zip_path) >=
        (int)sizeof(staging)) {
        AAsset_close(asset);
        return "Staging path too long";
    }
    FILE *out = fopen(staging, "wb");
    if (!out) {
        AAsset_close(asset);
        return "Cannot create Python archive";
    }
    char buffer[65536];
    int read_size;
    off64_t total = 0;
    int bad = 0;
    while ((read_size = AAsset_read(asset, buffer, sizeof(buffer))) > 0) {
        if (fwrite(buffer, 1, read_size, out) != (size_t)read_size) {
            bad = 1;
            break;
        }
        total += read_size;
    }
    int flush_failed = fflush(out);
    int close_failed = fclose(out);
    if (read_size < 0 || flush_failed || close_failed) bad = 1;
    AAsset_close(asset);
    if (!bad && total == expected && rename(staging, zip_path) == 0) return NULL;
    unlink(staging);
    return "Python archive extraction failed";
}

JNIEXPORT jstring JNICALL
Java_com_mene_exvius_LocalPythonProbe_execute(JNIEnv *env, jclass unused,
                                               jobject context) {
    (void)unused;
    if (!context) return (*env)->NewStringUTF(env, "no Context");
    char archive[PATH_MAX];
    const char *error = prepare_stdlib(env, context, archive, sizeof(archive));
    if (error) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "stdlib: %s", error);
        return (*env)->NewStringUTF(env, error);
    }
    if (Py_IsInitialized()) return (*env)->NewStringUTF(env, "already initialized");
    char dynload[PATH_MAX];
    char native_error[256] = {0};
    if (ffbe_prepare_dynload(env, context, archive, dynload, sizeof(dynload),
                             native_error, sizeof(native_error))) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "native: %s", native_error);
        return (*env)->NewStringUTF(env, native_error);
    }

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.site_import = 0;
    config.write_bytecode = 0;
    config.install_signal_handlers = 0;
    config.module_search_paths_set = 1;
    wchar_t *wide = Py_DecodeLocale(archive, NULL);
    if (!wide) return (*env)->NewStringUTF(env, "path decode failed");
    PyStatus status = PyWideStringList_Append(&config.module_search_paths, wide);
    PyMem_RawFree(wide);
    if (!PyStatus_Exception(status)) {
        wide = Py_DecodeLocale(dynload, NULL);
        if (!wide) {
            PyConfig_Clear(&config);
            return (*env)->NewStringUTF(env, "Native module path decode failed");
        }
        status = PyWideStringList_Append(&config.module_search_paths, wide);
        PyMem_RawFree(wide);
    }
    if (PyStatus_Exception(status)) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "sys.path: %s", status.err_msg);
        PyConfig_Clear(&config);
        return (*env)->NewStringUTF(env, "path config failed");
    }
    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "Py_Initialize: %s", status.err_msg);
        return (*env)->NewStringUTF(env, "initialization failed");
    }

    int code = PyRun_SimpleString(
        "import sys\n"
        "assert sys.version_info[:3] == (3, 14, 10)\n"
        "assert 6 * 7 == 42\n"
        "import zlib, binascii, ssl, sqlite3, socket, hashlib, json, zipfile\n"
        "assert ssl.OPENSSL_VERSION\n"
        "assert sqlite3.sqlite_version\n"
    );
    if (code) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "PyRun_SimpleString failed");
        return (*env)->NewStringUTF(env, "Python evaluation failed");
    }
    __android_log_print(ANDROID_LOG_INFO, TAG, "CPython 3.14.10: zlib ssl sqlite3 socket hashlib zipfile OK");
    int engine_status = PyRun_SimpleString(
        "import ffbe_engine_bootstrap\n"
        "ffbe_engine_bootstrap.probe()\n"
    );
    if (engine_status) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "Revival source import-only probe failed");
        return (*env)->NewStringUTF(env, "PYTHON-REVIVAL-IMPORT-FAILED");
    }
    __android_log_print(ANDROID_LOG_INFO, TAG,
                        "Revival imports: yaml tzdata/zoneinfo serve capture_server OK");
    return (*env)->NewStringUTF(env, "PYTHON-REVIVAL-TZDATA-OK");
}
