package com.careerpilot.careerpilot

import android.content.Context
import android.view.View
import androidx.camera.view.PreviewView
import io.flutter.plugin.common.StandardMessageCodec
import io.flutter.plugin.platform.PlatformView
import io.flutter.plugin.platform.PlatformViewFactory

/**
 * The live front-camera picture inside Flutter screens (the interview lobby, the interview itself,
 * the camera check). Each screen gets its own view; the newest one shows the camera. CameraX shows
 * the front camera mirrored, like a selfie, the same as the web app.
 */
class CameraPreviewFactory(private val tracker: FaceTracker) : PlatformViewFactory(StandardMessageCodec.INSTANCE) {
    override fun create(context: Context, viewId: Int, args: Any?): PlatformView {
        val view = PreviewView(context).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE   // works inside Flutter
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
        tracker.attach(view)
        return object : PlatformView {
            override fun getView(): View = view
            override fun dispose() = tracker.detach(view)
        }
    }
}
