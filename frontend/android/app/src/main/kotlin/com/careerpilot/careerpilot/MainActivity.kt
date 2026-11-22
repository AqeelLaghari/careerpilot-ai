package com.careerpilot.careerpilot

import android.content.pm.PackageManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {
    private var faceTracker: FaceTracker? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // Camera + face tracking for the live interview (see FaceTracker.kt)
        val tracker = FaceTracker(this, flutterEngine.dartExecutor.binaryMessenger)
        faceTracker = tracker
        flutterEngine.platformViewsController.registry
            .registerViewFactory("careerpilot/camera-preview", CameraPreviewFactory(tracker))
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == FaceTracker.CAMERA_REQUEST) {
            faceTracker?.onPermissionResult(grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED)
        }
    }

    override fun onDestroy() {
        faceTracker?.stop()
        super.onDestroy()
    }
}
