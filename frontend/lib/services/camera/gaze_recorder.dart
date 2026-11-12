import 'dart:async';

import 'face_camera.dart';

/// Writes down where the user looks while answering: one letter per look, [fps] looks a
/// second (codes in backend/app/services/eye_contact.py). Only these letters are sent.
class GazeRecorder {
  GazeRecorder(this.camera, {this.fps = 5});
  final FaceCamera camera;
  final int fps;
  final _codes = StringBuffer();
  Timer? _timer;

  static String codeFor(FaceSample s) {
    if (!s.face) return 'N';
    if (s.faces > 1) return 'M';
    if (s.calibrating) return 'S';
    if (s.eyesOpen < 0.12) return 'B';
    if (s.headYaw < -0.35) return 'L';
    if (s.headYaw > 0.35) return 'R';
    if (s.headPitch < -0.4) return 'U';
    if (s.headPitch > 0.4) return 'D';
    if (s.gazeH < -0.35) return 'l';
    if (s.gazeH > 0.35) return 'r';
    if (s.gazeV < -0.4) return 'u';
    if (s.gazeV > 0.4) return 'd';
    return 'S';
  }

  void start() {
    _codes.clear();
    _timer?.cancel();
    _timer = Timer.periodic(Duration(milliseconds: 1000 ~/ fps), (_) {
      final s = camera.latest();
      if (s.status == 'ready') _codes.write(codeFor(s));
    });
  }

  /// Stop and return the letters ('' if the camera was not tracking).
  String stop() {
    _timer?.cancel();
    _timer = null;
    return _codes.toString();
  }
}
