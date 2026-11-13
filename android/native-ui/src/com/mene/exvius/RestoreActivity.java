package com.mene.exvius;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.InputStream;

/** LAB ONLY: user-initiated local ZIP selection; NEVER writes a game save. */
public final class RestoreActivity extends Activity {
    private static final int PICK_ZIP = 7011;
    private TextView status;
    private TextView details;
    private EditText confirmation;
    private Button schedule;
    private Button browse;
    private Button cancel;
    private RestoreRequestCodec.Preview preview;
    private volatile boolean busy;

    private int dp(int amount) {
        return (int)(getResources().getDisplayMetrics().density * amount + 0.5f);
    }

    private TextView label(String text, float size, LinearLayout parent) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setPadding(0, dp(8), 0, dp(8));
        parent.addView(view, new LinearLayout.LayoutParams(-1, -2));
        return view;
    }

    private Button button(String text, LinearLayout parent, View.OnClickListener listener) {
        Button result = new Button(this);
        result.setText(text);
        result.setAllCaps(false);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.topMargin = dp(8);
        parent.addView(result, p);
        result.setOnClickListener(listener);
        return result;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        setTitle("FFBE • Restaurar save");
        ScrollView scroll = new ScrollView(this);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(20), dp(20), dp(20), dp(32));
        scroll.addView(column);
        setContentView(scroll);
        label("Restaurar progresso", 24, column);
        label("Selecione um ZIP de backup. O save atual será preservado antes de qualquer alteração. " +
              "A restauração ocorrerá somente na próxima inicialização completa do FFBE.", 15, column);
        browse = button("Escolher arquivo ZIP", column, new View.OnClickListener() {
            @Override public void onClick(View view) { chooseZip(); }
        });
        details = label("Nenhum backup selecionado.", 14, column);
        confirmation = new EditText(this);
        confirmation.setSingleLine(true);
        confirmation.setHint("Digite RESTAURAR seguido do código exibido");
        confirmation.setContentDescription("Confirmação da restauração");
        column.addView(confirmation, new LinearLayout.LayoutParams(-1, -2));
        schedule = button("Agendar para próxima abertura", column, new View.OnClickListener() {
            @Override public void onClick(View view) { stageRequest(); }
        });
        schedule.setEnabled(false);
        cancel = button("Cancelar pedido pendente", column, new View.OnClickListener() {
            @Override public void onClick(View view) { cancelRequest(); }
        });
        status = label("Esta tela nunca modifica os arquivos do jogo enquanto ele está aberto.", 14, column);
        label("Atenção: após agendar, feche completamente o FFBE e só então abra o jogo. " +
              "Não remova os dados do aplicativo. Restaurações reais ainda exigem validação em laboratório.", 13, column);
    }

    private void chooseZip() {
        if (busy) return;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/zip");
        startActivityForResult(intent, PICK_ZIP);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_ZIP || resultCode != RESULT_OK || data == null || data.getData() == null)
            return;
        final Uri uri = data.getData();
        busy = true;
        schedule.setEnabled(false);
        browse.setEnabled(false);
        status.setText("Lendo arquivo selecionado...");
        new Thread(new Runnable() {
            @Override public void run() {
                try (InputStream input = getContentResolver().openInputStream(uri)) {
                    final RestoreRequestCodec.Preview selected = RestoreRequestCodec.preview(input);
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            if (isFinishing() || isDestroyed()) return;
                            preview = selected;
                            details.setText("Tamanho: " + selected.data.length + " bytes\nSHA-256: " +
                                selected.sha256 + "\nPara confirmar: " + selected.confirmation);
                            status.setText("Confira o hash antes de agendar. O conteúdo ZIP será validado novamente no início.");
                            busy = false;
                            browse.setEnabled(true);
                            schedule.setEnabled(true);
                        }
                    });
                } catch (final Exception error) {
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            if (isFinishing() || isDestroyed()) return;
                            preview = null;
                            details.setText("Nenhum arquivo válido selecionado.");
                            status.setText("Falha na seleção: " + error.getClass().getSimpleName());
                            busy = false;
                            browse.setEnabled(true);
                            schedule.setEnabled(false);
                        }
                    });
                }
            }
        }, "FFBE-Restore-Read").start();
    }

    private void stageRequest() {
        final RestoreRequestCodec.Preview selected = preview;
        if (busy || selected == null) return;
        final String typed = confirmation.getText().toString();
        if (!selected.confirmation.equals(typed)) {
            confirmation.setError("Confirmação diferente do código solicitado");
            return;
        }
        busy = true;
        browse.setEnabled(false);
        schedule.setEnabled(false);
        status.setText("Preparando pedido privado...");
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    RestoreRequestCodec.stage(getFilesDir().toPath(), selected, typed);
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            if (isFinishing() || isDestroyed()) return;
                            busy = false;
                            preview = null;
                            status.setText("Pedido confirmado. Feche o FFBE completamente e reabra. " +
                                "A restauração usará pré-backup e verificação de integridade.");
                            browse.setEnabled(true);
                            schedule.setEnabled(false);
                        }
                    });
                } catch (final Exception error) {
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            if (isFinishing() || isDestroyed()) return;
                            busy = false;
                            browse.setEnabled(true);
                            schedule.setEnabled(true);
                            status.setText("Não foi possível agendar: " + error.getMessage());
                        }
                    });
                }
            }
        }, "FFBE-Restore-Stage").start();
    }

    private void cancelRequest() {
        if (busy) return;
        busy = true;
        cancel.setEnabled(false);
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    final boolean canceled = RestoreRequestCodec.cancelQueued(getFilesDir().toPath());
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            if (isFinishing() || isDestroyed()) return;
                            busy = false;
                            cancel.setEnabled(true);
                            status.setText(canceled ? "Pedido cancelado. Nenhum save foi alterado." :
                                "Não há pedido aguardando execução.");
                        }
                    });
                } catch (final Exception error) {
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            if (isFinishing() || isDestroyed()) return;
                            busy = false;
                            cancel.setEnabled(true);
                            status.setText("Pedido não cancelado: " + error.getMessage());
                        }
                    });
                }
            }
        }, "FFBE-Restore-Cancel").start();
    }
}
