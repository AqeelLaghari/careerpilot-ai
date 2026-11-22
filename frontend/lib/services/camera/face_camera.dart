// Camera + face tracking.
//   Web:     the browser camera and MediaPipe in JavaScript (web/face_tracker.js)
//   Android: CameraX and MediaPipe for Android (FaceTracker.kt), same model and maths (face_math.dart)
//   Others (Windows desktop, tests): FaceCamera.supported is false and nothing starts
export 'face_camera_stub.dart'
    if (dart.library.js_interop) 'face_camera_web.dart'
    if (dart.library.io) 'face_camera_mobile.dart';
export 'face_sample.dart';
