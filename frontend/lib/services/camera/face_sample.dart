/// One measurement from the face tracker (see web/face_tracker.js for the meaning of each value).
class FaceSample {
  const FaceSample({
    required this.status,
    this.error,
    this.face = false,
    this.faces = 0,
    this.fps = 0,
    this.gazeH = 0,
    this.gazeV = 0,
    this.headYaw = 0,
    this.headPitch = 0,
    this.eyesOpen = 0,
    this.calibrated = false,
    this.calibrating = false,
  });

  static const off = FaceSample(status: 'off');

  /// off, camera_on, loading, ready, camera_ended, error
  final String status;
  final String? error;
  final bool face;
  final int faces;
  final int fps;
  final double gazeH; // -1 eyes to your left ... +1 right
  final double gazeV; // -1 up ... +1 down
  final double headYaw; // -1 head turned left ... +1 right
  final double headPitch; // -1 up ... +1 down
  final double eyesOpen; // ~0.3 open, < 0.12 closed / blinking
  final bool calibrated; // centre = the user's own normal position
  final bool calibrating;

  factory FaceSample.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return FaceSample(
      status: j['status'] as String? ?? 'off',
      error: j['error'] as String?,
      face: j['face'] == true,
      faces: (j['faces'] as num?)?.toInt() ?? 0,
      fps: (j['fps'] as num?)?.toInt() ?? 0,
      gazeH: d('gaze_h'),
      gazeV: d('gaze_v'),
      headYaw: d('head_yaw'),
      headPitch: d('head_pitch'),
      eyesOpen: d('eyes_open'),
      calibrated: j['calibrated'] == true,
      calibrating: j['calibrating'] == true,
    );
  }

  /// Rough direction for the camera check. (Day 19 replaces this with a calibrated eye-contact score.)
  String get direction {
    if (!face) return 'No face in view';
    if (calibrating) return 'Look at the middle of the screen…';
    if (faces > 1) return 'More than one face';
    if (eyesOpen < 0.12) return 'Eyes closed / blinking';
    if (headYaw < -0.35) return 'Head turned left';
    if (headYaw > 0.35) return 'Head turned right';
    if (gazeH < -0.35) return 'Eyes looking left';
    if (gazeH > 0.35) return 'Eyes looking right';
    if (headPitch < -0.4) return 'Head tilted up';
    if (headPitch > 0.4) return 'Head tilted down';
    if (gazeV < -0.4) return 'Eyes looking up';
    if (gazeV > 0.4) return 'Eyes looking down';
    return 'Looking at the screen';
  }

  bool get lookingAtScreen => direction == 'Looking at the screen';
}
