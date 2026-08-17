package io.qoresence.glass;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(QoreMdnsPlugin.class);
        registerPlugin(QoreBackgroundPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
