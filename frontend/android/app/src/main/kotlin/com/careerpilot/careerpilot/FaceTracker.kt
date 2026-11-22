package com.careerpilot.careerpilot

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import io.flutter.embedding.android.FlutterActivity
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.util.concurrent.Executors

/**
 * Camera + face tracking for the live interview on Android (the phone edition of web/face_tracker.js).
 *
 * The front camera runs with CameraX. Google's MediaPipe Face Landmarker (the same model file as in
 * the web app) finds 478 face points, including both irises, about 15 times a second. Only the 13
 * points the gaze maths needs are sent to Flutter (lib/services/camera/face_math.dart does the same
 * calculations as the web). The video never leaves the phone.
 *
 * Flutter talks to it through:
 *   MethodChannel "careerpilot/face":        start() -> "ok" | NotAllowedError | NotFoundError | NotReadableError,
 *                                            track() -> "ok" | "error", stop()
 *   EventChannel  "careerpilot/face/events": {status, error} or one frame {faces, fps, w, h, pts}
 *   Platform view "careerpilot/camera-preview": the live picture (see CameraPreviewFactory)
 */
class FaceTracker(private val activity: FlutterActivity, messenger: BinaryMessenger) :
    MethodChannel.MethodCallHandler, EventChannel.StreamHandler {

    companion object {
        const val CAMERA_REQUEST = 4711
        private const val TARGET_FPS = 15
        private const val MODEL_URL =
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

        // Face mesh points used by the gaze maths: eye corners, eyelids, irises, nose tip, cheeks
        val POINTS = intArrayOf(33, 133, 159, 145, 468, 362, 263, 386, 374, 473, 1, 234, 454)
    }

    private val main = Handler(Looper.getMainLooper())
    private val analysisThread = Executors.newSingleThreadExecutor()
    private var sink: EventChannel.EventSink? = null

    private var provider: ProcessCameraProvider? = null
    private var preview: Preview? = null
    private val views = mutableListOf<PreviewView>()   // on-screen pictures; the newest one is live
    private var pendingStart: MethodChannel.Result? = null

    @Volatile private var landmarker: FaceLandmarker? = null
    @Volatile private var tracking = false
    private var loading = false
    private var lastRun = 0L
    private var frames = 0
    private var fpsStart = 0L
    private var fps = 0

    init {
        MethodChannel(messenger, "careerpilot/face").setMethodCallHandler(this)
        EventChannel(messenger, "careerpilot/face/events").setStreamHandler(this)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "start" -> start(result)
            "track" -> track(result)
            "stop" -> { stop(); result.success(null) }
            else -> result.notImplemented()
        }
    }

    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) { sink = events }
    override fun onCancel(arguments: Any?) { sink = null }

    private fun send(event: Map<String, Any?>) = main.post { sink?.success(event) }

    // ---- camera -------------------------------------------------------------------------------

    private fun start(result: MethodChannel.Result) {
        if (provider != null) { result.success("ok"); return }
        if (ContextCompat.checkSelfPermission(activity, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            bindCamera(result)
        } else {
            pendingStart?.success("NotAllowedError")
            pendingStart = result
            ActivityCompat.requestPermissions(activity, arrayOf(Manifest.permission.CAMERA), CAMERA_REQUEST)
        }
    }

    /** Called by MainActivity with the answer to the camera permission question. */
    fun onPermissionResult(granted: Boolean) {
        val result = pendingStart ?: return
        pendingStart = null
        if (granted) bindCamera(result) else result.success("NotAllowedError")
    }

    private fun bindCamera(result: MethodChannel.Result) {
        val future = ProcessCameraProvider.getInstance(activity)
        future.addListener({
            try {
                val p = future.get()
                val selector = CameraSelector.DEFAULT_FRONT_CAMERA
                if (!p.hasCamera(selector)) { result.success("NotFoundError"); return@addListener }
                val pv = Preview.Builder().build()
                val analysis = ImageAnalysis.Builder()
                    .setResolutionSelector(
                        ResolutionSelector.Builder().setResolutionStrategy(
                            ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
                        ).build()
                    )
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .build()
                analysis.setAnalyzer(analysisThread) { analyze(it) }
                p.unbindAll()
                p.bindToLifecycle(activity, selector, pv, analysis)
                provider = p
                preview = pv
                views.lastOrNull()?.let { pv.setSurfaceProvider(it.surfaceProvider) }
                send(mapOf("status" to "camera_on"))
                result.success("ok")
            } catch (e: Throwable) {
                result.success("NotReadableError")
            }
        }, ContextCompat.getMainExecutor(activity))
    }

    fun attach(view: PreviewView) {
        views.add(view)
        preview?.setSurfaceProvider(view.surfaceProvider)
    }

    fun detach(view: PreviewView) {
        views.remove(view)
        preview?.setSurfaceProvider(views.lastOrNull()?.surfaceProvider)
    }

    fun stop() {
        tracking = false
        provider?.unbindAll()
        provider = null
        preview = null
        send(mapOf("status" to "off"))
    }

    // ---- face tracking ------------------------------------------------------------------------

    private fun track(result: MethodChannel.Result) {
        if (provider == null) { result.success("no_camera"); return }
        if (landmarker != null) { tracking = true; result.success("ok"); return }
        if (loading) { result.success("ok"); return }
        loading = true
        send(mapOf("status" to "loading"))
        Thread {
            try {
                val options = FaceLandmarker.FaceLandmarkerOptions.builder()
                    .setBaseOptions(BaseOptions.builder().setModelAssetBuffer(model()).setDelegate(Delegate.CPU).build())
                    .setRunningMode(RunningMode.VIDEO)
                    .setNumFaces(2)
                    .build()
                landmarker = FaceLandmarker.createFromOptions(activity, options)
                tracking = provider != null
                main.post { loading = false; result.success("ok") }
            } catch (e: Throwable) {   // Throwable: a native library error must not close the app
                send(mapOf("status" to "error", "error" to "Face tracking could not load: ${e.message}"))
                main.post { loading = false; result.success("error") }
            }
        }.start()
    }

    /** The face model (about 3.6 MB): downloaded once, like the web app, then kept on the phone. */
    private fun model(): ByteBuffer {
        val file = File(activity.filesDir, "face_landmarker.task")
        if (!file.exists() || file.length() < 1_000_000) {
            val tmp = File(activity.filesDir, "face_landmarker.task.part")
            val conn = URL(MODEL_URL).openConnection() as HttpURLConnection
            conn.connectTimeout = 15_000
            conn.readTimeout = 30_000
            try {
                conn.inputStream.use { input -> tmp.outputStream().use { input.copyTo(it) } }
            } finally {
                conn.disconnect()
            }
            if (!tmp.renameTo(file)) throw IllegalStateException("could not save the face model")
        }
        return FileInputStream(file).channel.use { it.map(FileChannel.MapMode.READ_ONLY, 0, it.size()) }
    }

    private fun analyze(image: ImageProxy) {
        try {
            val lm = landmarker
            if (!tracking || lm == null) return
            val now = SystemClock.uptimeMillis()
            if (now - lastRun < 1000L / TARGET_FPS) return
            lastRun = now
            // Upright picture, NOT mirrored (like the browser's camera frames): face_math.dart turns
            // the result into the user's own (mirror) view, exactly as the web code does.
            val raw = image.toBitmap()
            val rotation = image.imageInfo.rotationDegrees
            val bitmap = if (rotation == 0) raw else Bitmap.createBitmap(
                raw, 0, 0, raw.width, raw.height, Matrix().apply { postRotate(rotation.toFloat()) }, true
            )
            val result = lm.detectForVideo(BitmapImageBuilder(bitmap).build(), now)
            frames++
            if (fpsStart == 0L) fpsStart = now
            if (now - fpsStart >= 1000) {
                fps = (frames * 1000 / (now - fpsStart)).toInt()
                frames = 0
                fpsStart = now
            }
            val faces = result.faceLandmarks()
            val event = HashMap<String, Any?>()
            event["faces"] = faces.size
            event["fps"] = fps
            event["w"] = bitmap.width
            event["h"] = bitmap.height
            if (faces.isNotEmpty()) {
                val face = faces[0]
                val pts = ArrayList<Double>(POINTS.size * 2)
                for (i in POINTS) {
                    pts.add(face[i].x().toDouble())
                    pts.add(face[i].y().toDouble())
                }
                event["pts"] = pts
            }
            send(event)
        } catch (e: Throwable) {
            send(mapOf("status" to "error", "error" to e.toString()))
        } finally {
            image.close()
        }
    }
}
