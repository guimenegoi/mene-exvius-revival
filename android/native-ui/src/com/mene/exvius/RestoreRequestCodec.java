package com.mene.exvius;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;

/** Device-side request staging ONLY. Never opens/modifies active game saves. */
public final class RestoreRequestCodec {
    public static final int MAX_ZIP_BYTES = 20 * 1024 * 1024;
    private static final String QUEUE = "restore-request.json";
    private static final String PROCESSING = "restore-processing.json";
    private static final String JOURNAL = "pending-restore.json";

    private RestoreRequestCodec() {}

    public static final class Preview {
        public final byte[] data;
        public final String sha256;
        public final String confirmation;
        private Preview(byte[] bytes, String sha) {
            data = bytes;
            sha256 = sha;
            confirmation = "RESTAURAR " + sha.substring(0, 12);
        }
    }

    public static Preview preview(InputStream input) throws IOException {
        if (input == null) throw new IOException("Arquivo ZIP inacessível");
        byte[] buffer = new byte[8192];
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (count == 0) continue;
            if ((long)out.size() + count > MAX_ZIP_BYTES)
                throw new IOException("ZIP maior que 20 MiB");
            out.write(buffer, 0, count);
        }
        byte[] bytes = out.toByteArray();
        if (bytes.length == 0) throw new IOException("ZIP vazio");
        return new Preview(bytes, sha256(bytes));
    }

    static String sha256(byte[] data) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(data);
            char[] chars = new char[hash.length * 2];
            final char[] hex = "0123456789abcdef".toCharArray();
            for (int i = 0; i < hash.length; i++) {
                chars[2*i] = hex[(hash[i] >>> 4) & 15];
                chars[2*i+1] = hex[hash[i] & 15];
            }
            return new String(chars);
        } catch (NoSuchAlgorithmException e) {
            throw new AssertionError("SHA-256 unavailable", e);
        }
    }

    static Path recoveryPath(Path appFiles) {
        return appFiles.resolve("exvius").resolve("server-root")
                .resolve("restore-private");
    }

    private static boolean present(Path path) {
        return Files.exists(path, LinkOption.NOFOLLOW_LINKS);
    }

    private static void privateFile(Path path) throws IOException {
        Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rw-------"));
    }

    private static void syncDir(Path dir) throws IOException {
        try (FileChannel channel = FileChannel.open(dir, StandardOpenOption.READ)) {
            channel.force(true);
        }
    }

    private static void writePrivate(Path path, byte[] data) throws IOException {
        try (FileChannel channel = FileChannel.open(path, StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING)) {
            ByteBuffer buffer = ByteBuffer.wrap(data);
            while (buffer.hasRemaining()) channel.write(buffer);
            channel.force(true);
        }
    }

    private static void atomicInstall(Path temp, Path target, Path parent) throws IOException {
        if (present(target)) throw new IOException("Arquivo já existente; operação cancelada");
        try {
            Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            throw new IOException("Dispositivo sem gravação atômica", e);
        }
        syncDir(parent);
    }

    private static Path checkedRoot(Path appFiles) throws IOException {
        Path root = appFiles.toAbsolutePath().normalize();
        Path serverRoot = root.resolve("exvius/server-root");
        Path state = serverRoot.resolve("state");
        Path campaign = state.resolve("campaign.json");
        if (!Files.isDirectory(state, LinkOption.NOFOLLOW_LINKS) ||
                !Files.isRegularFile(campaign, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Save ativo não encontrado; nenhum pedido criado");
        Path recovery = recoveryPath(root);
        if (present(recovery) && !Files.isDirectory(recovery, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Diretório de restauração inválido");
        Files.createDirectories(recovery);
        Files.setPosixFilePermissions(recovery, PosixFilePermissions.fromString("rwx------"));
        return recovery;
    }

    /** Persist a confirmed request. The Python cold-start guard performs restore. */
    public static void stage(Path appFiles, Preview preview, String typed) throws IOException {
        if (preview == null || typed == null || !preview.confirmation.equals(typed))
            throw new IOException("Confirmação incorreta");
        if (preview.data.length == 0 || preview.data.length > MAX_ZIP_BYTES ||
                !sha256(preview.data).equals(preview.sha256))
            throw new IOException("ZIP inválido ou alterado");
        Path root = checkedRoot(appFiles);
        if (present(root.resolve(QUEUE)) || present(root.resolve(PROCESSING)) ||
                present(root.resolve(JOURNAL)))
            throw new IOException("Já existe uma restauração pendente");
        String zipName = "request-" + preview.sha256 + ".zip";
        Path zip = root.resolve(zipName);
        if (present(zip)) throw new IOException("ZIP já preparado anteriormente");
        Path zipTemp = Files.createTempFile(root, ".zip-stage-", ".tmp");
        try {
            privateFile(zipTemp);
            writePrivate(zipTemp, preview.data);
            atomicInstall(zipTemp, zip, root);
        } finally {
            Files.deleteIfExists(zipTemp);
        }
        String json = "{\"schema\":1,\"archive\":\"" + zipName +
            "\",\"sha256\":\"" + preview.sha256 +
            "\",\"confirmation\":\"" + preview.confirmation + "\"}";
        Path metaTemp = Files.createTempFile(root, ".request-stage-", ".tmp");
        try {
            privateFile(metaTemp);
            writePrivate(metaTemp, json.getBytes(StandardCharsets.US_ASCII));
            atomicInstall(metaTemp, root.resolve(QUEUE), root);
        } finally {
            Files.deleteIfExists(metaTemp);
        }
    }

    /** Cancel only a QUEUED request; never cancel a processing journal. */
    public static boolean cancelQueued(Path appFiles) throws IOException {
        Path root = recoveryPath(appFiles.toAbsolutePath().normalize());
        if (present(root.resolve(JOURNAL)) || present(root.resolve(PROCESSING)))
            throw new IOException("Restauração já em andamento: não pode cancelar");
        Path request = root.resolve(QUEUE);
        if (!present(request)) return false;
        if (!Files.isRegularFile(request, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Pedido inválido");
        Files.delete(request);
        syncDir(root);
        // Only remove known staging ZIP filenames, never pre-restore backups.
        // This also cleans orphaned ZIPs from a canceled/incomplete selection.
        try (DirectoryStream<Path> staged = Files.newDirectoryStream(root, "request-*.zip")) {
            for (Path zip : staged) {
                String name = zip.getFileName().toString();
                if (name.matches("request-[a-f0-9]{64}\\.zip") &&
                        Files.isRegularFile(zip, LinkOption.NOFOLLOW_LINKS))
                    Files.delete(zip);
            }
        }
        syncDir(root);
        return true;
    }
}
