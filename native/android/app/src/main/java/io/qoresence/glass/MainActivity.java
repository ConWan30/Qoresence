package io.qoresence.glass;

import android.app.PictureInPictureParams;
import android.os.Build;
import android.os.Bundle;
import android.util.Rational;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(QoreMdnsPlugin.class);
        registerPlugin(QoreBackgroundPlugin.class);
        registerPlugin(QoreCinemaPlugin.class);
        super.onCreate(savedInstanceState);
    }

    @Override
    public void onUserLeaveHint() {
        super.onUserLeaveHint();
        enterPipIfAuto();
    }

    @Override
    public void onPictureInPictureModeChanged(boolean isInPictureInPictureMode) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode);
        QoreCinemaPlugin.notifyPipChanged(isInPictureInPictureMode);
    }

    private void enterPipIfAuto() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && QoreCinemaPlugin.autoPipEnabled()) {
            try {
                PictureInPictureParams params = new PictureInPictureParams.Builder()
                    .setAspectRatio(new Rational(16, 9))
                    .build();
                enterPictureInPictureMode(params);
            } catch (Exception ignored) {
            }
        }
    }
}
