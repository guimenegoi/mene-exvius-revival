package com.mene.exvius;

import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public final class RestoreRequestCodecTest {
  static void check(boolean yes) { if (!yes) throw new AssertionError(); }
  static void expectFail(RunnableWithIO task) throws Exception { try { task.run(); throw new AssertionError("expected refusal"); } catch(java.io.IOException expected) {} }
  interface RunnableWithIO { void run() throws Exception; }
  public static void main(String[] args) throws Exception {
    Path root=Files.createTempDirectory("restore-java-test-");
    Path state=root.resolve("exvius/server-root/state");
    Files.createDirectories(state);
    Files.writeString(state.resolve("campaign.json"),"{\"rank\":50}");
    byte[] bytes=new byte[]{'P','K',3,4,0,1,2,3,4,5}; // Only staged, never applied
    RestoreRequestCodec.Preview preview=RestoreRequestCodec.preview(new ByteArrayInputStream(bytes));
    check(preview.sha256.length()==64);
    check(preview.confirmation.equals("RESTAURAR "+preview.sha256.substring(0,12)));
    expectFail(()->RestoreRequestCodec.stage(root,preview,"INCORRETO"));
    check(!Files.exists(RestoreRequestCodec.recoveryPath(root).resolve("restore-request.json")));
    RestoreRequestCodec.stage(root,preview,preview.confirmation);
    Path r=RestoreRequestCodec.recoveryPath(root);
    check(Files.isRegularFile(r.resolve("restore-request.json")));
    check(Files.isRegularFile(r.resolve("request-"+preview.sha256+".zip")));
    check(Files.readString(state.resolve("campaign.json")).contains("50"));
    expectFail(()->RestoreRequestCodec.stage(root,preview,preview.confirmation));
    check(RestoreRequestCodec.cancelQueued(root));
    check(!RestoreRequestCodec.cancelQueued(root));
    check(!Files.exists(r.resolve("restore-request.json")));
    Files.writeString(r.resolve("restore-processing.json"),"{}");
    expectFail(()->RestoreRequestCodec.cancelQueued(root));
    Files.delete(r.resolve("restore-processing.json"));
    try (Stream<Path> paths=Files.walk(root)) { paths.sorted(java.util.Comparator.reverseOrder()).forEach(p->{try{Files.delete(p);}catch(Exception x){throw new RuntimeException(x);}}); }
    System.out.println("RestoreRequestCodec tests: OK");
  }
}
