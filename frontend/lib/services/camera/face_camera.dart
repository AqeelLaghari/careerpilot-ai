// Camera + face tracking. Web: the browser camera and MediaPipe (web/face_tracker.js).
// Other platforms: not available yet (the phone pass comes later), so a stub is used.
export 'face_camera_stub.dart' if (dart.library.js_interop) 'face_camera_web.dart';
export 'face_sample.dart';
