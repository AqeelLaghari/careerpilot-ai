import 'dart:math' as math;

import 'face_sample.dart';

/// The gaze maths of web/face_tracker.js, ported line by line for the Android app, so a phone
/// interview is measured exactly like a web one (same landmarks, same formulas, same constants).
///
/// Input: the 13 MediaPipe face-mesh points sent by FaceTracker.kt (normalised 0..1 in an upright,
/// NOT mirrored camera picture, like the browser's video frames). Output: [FaceSample].
class FaceMath {
  FaceMath({double Function()? clock}) : _clock = clock ?? (() => DateTime.now().millisecondsSinceEpoch.toDouble());

  final double Function() _clock;

  /// Face-mesh point numbers sent by FaceTracker.kt, in this order.
  static const points = [33, 133, 159, 145, 468, 362, 263, 386, 374, 473, 1, 234, 454];

  // Landmark numbers in the MediaPipe face mesh (478 points with irises), as in face_tracker.js
  static const _eyes = [
    (corners: [33, 133], lids: [159, 145], iris: 468),
    (corners: [362, 263], lids: [386, 374], iris: 473),
  ];
  static const _nose = 1, _cheekA = 234, _cheekB = 454;

  // Sensitivity: how much raw change moves a value from the centre to the end (+-1)
  static const _scaleH = 2.0, _scaleV = 9.0, _scaleOpen = 4.0, _scaleYaw = 2.0, _scalePitch = 4.0;

  Raw? base;
  _Calib? _calib;
  List<Raw>? _listen;

  /// One event from FaceTracker.kt: a status ({status, error}) or a frame ({faces, fps, w, h, pts}).
  FaceSample onEvent(Map<Object?, Object?> e) {
    final status = e['status'];
    if (status is String) return FaceSample(status: status, error: e['error'] as String?);
    final faces = (e['faces'] as num?)?.toInt() ?? 0;
    final fps = (e['fps'] as num?)?.toInt() ?? 0;
    final pts = e['pts'] as List?;
    if (faces == 0 || pts == null || pts.length < points.length * 2) {
      return FaceSample(status: 'ready', fps: fps, calibrated: base != null, calibrating: _calib != null);
    }
    final w = (e['w'] as num).toDouble(), h = (e['h'] as num).toDouble();
    final lm = <int, Pt>{
      for (var i = 0; i < points.length; i++)
        points[i]: toTrackerSpace((pts[2 * i] as num).toDouble(), (pts[2 * i + 1] as num).toDouble(), w, h),
    };
    return measure(lm, faces: faces, fps: fps, now: _clock());
  }

  /// The web app reads 640x480 frames, so its normalised points are (px / 640, py / 480). A phone
  /// picture has another shape (often 480x640, portrait); scaling to (px / 4, py / 3) gives points
  /// with the same proportions as the web, and every formula below uses only ratios, so the same face
  /// gives the same numbers on both.
  static Pt toTrackerSpace(double x, double y, double w, double h) => Pt(x * w / 4, y * h / 3);

  static double _along(Pt p, Pt a, Pt b) {
    final dx = b.x - a.x, dy = b.y - a.y;
    final len2 = dx * dx + dy * dy;
    return ((p.x - a.x) * dx + (p.y - a.y) * dy) / (len2 == 0 ? 1e-6 : len2);
  }

  static double _dist(Pt a, Pt b) {
    final d = math.sqrt((b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y));
    return d == 0 ? 1e-6 : d;
  }

  /// The raw measurements of one face (face_tracker.js `raw`).
  static Raw raw(Map<int, Pt> lm) {
    var h = 0.0, v = 0.0, open = 0.0;
    for (final e in _eyes) {
      // corners sorted left->right in the camera image, so both eyes are measured the same way
      var a = lm[e.corners[0]]!, b = lm[e.corners[1]]!;
      if (a.x > b.x) (a, b) = (b, a);
      final iris = lm[e.iris]!;
      final w = _dist(a, b);
      h += _along(iris, a, b);
      // up/down: how far the iris is from the line between the eye corners, as a share of the eye width
      final cross = ((b.x - a.x) * (iris.y - a.y) - (b.y - a.y) * (iris.x - a.x)) / w;
      v += cross / w;
      final up = lm[e.lids[0]]!, down = lm[e.lids[1]]!;
      open += _dist(up, down) / w;
    }
    h /= 2;
    v /= 2;
    open /= 2;
    final nose = lm[_nose]!, ca = lm[_cheekA]!, cb = lm[_cheekB]!;
    final left = ca.x < cb.x ? ca : cb, right = ca.x < cb.x ? cb : ca;
    // head up/down: nose tip below the line between the eyes, as a share of the eye distance
    final eyeL = lm[_eyes[0].iris]!, eyeR = lm[_eyes[1].iris]!;
    final eyeDist = _dist(eyeL, eyeR);
    final noseDrop =
        ((eyeR.x - eyeL.x) * (nose.y - eyeL.y) - (eyeR.y - eyeL.y) * (nose.x - eyeL.x)) / (eyeDist * eyeDist);
    return Raw(h: h, v: v, open: open, yaw: _along(nose, left, right), pitch: noseDrop.abs());
  }

  static double _clamp(double x) => x.clamp(-1.5, 1.5).toDouble();
  static double _r3(double x) => (x * 1000).round() / 1000;

  // ---- calibration: the user's normal "looking at the screen" position becomes the centre ----

  void _calibrate(double now, [double ms = 1500]) => _calib = _Calib(now + ms);

  /// "Recalibrate" button: the next 1.5 s of looking at the screen become the new centre.
  void recalibrate() {
    base = null;
    _calibrate(_clock());
  }

  /// Live interview: while the interviewer speaks, the user looks at the screen; the median of that
  /// time becomes "straight ahead" for the next answer.
  void baselineStart() => _listen = [];

  int baselineEnd() {
    final rows = _listen ?? const <Raw>[];
    _listen = null;
    if (rows.length < 8) return 0; // under ~0.5 s of a clear face: keep the old one
    double med(double Function(Raw) f) {
      final s = rows.map(f).toList()..sort();
      final n = s.length;
      return n.isOdd ? s[(n - 1) ~/ 2] : (s[n ~/ 2 - 1] + s[n ~/ 2]) / 2;
    }

    base = Raw(
      h: med((r) => r.h),
      v: med((r) => r.v),
      open: med((r) => r.open),
      yaw: med((r) => r.yaw),
      pitch: med((r) => r.pitch),
    );
    _calib = null;
    return rows.length;
  }

  /// face_tracker.js `measure`, for the first face.
  FaceSample measure(Map<int, Pt> lm, {required int faces, required int fps, required double now}) {
    final m = raw(lm);
    final listen = _listen;
    if (listen != null && faces == 1 && m.open > 0.12 && listen.length < 1500) listen.add(m);
    if (base == null && _calib == null) _calibrate(now); // first time a face is seen
    final calib = _calib;
    if (calib != null) {
      if (faces == 1 && m.open > 0.12) calib.rows.add(m); // skip blinks
      if (now >= calib.until && calib.rows.length >= 5) {
        double avg(double Function(Raw) f) => calib.rows.map(f).reduce((a, b) => a + b) / calib.rows.length;
        base = Raw(
          h: avg((r) => r.h),
          v: avg((r) => r.v),
          open: avg((r) => r.open),
          yaw: avg((r) => r.yaw),
          pitch: avg((r) => r.pitch),
        );
        _calib = null;
      } else if (now >= calib.until + 3000) {
        _calib = null; // no clear face: try again next time
      }
    }
    final b = base ?? Raw(h: 0.5, v: 0, open: m.open, yaw: 0.5, pitch: m.pitch);
    // camera image -> mirror view: moving right in the image = the user's left
    final gazeH = -(m.h - b.h) * _scaleH * 2;
    // eyes down: iris drops below the corner line AND the eyelids close a little
    final gazeV = (m.v - b.v) * _scaleV - (m.open - b.open) * _scaleOpen;
    final yaw = -(m.yaw - b.yaw) * _scaleYaw * 2;
    final pitch = (m.pitch - b.pitch) * _scalePitch;
    return FaceSample(
      status: 'ready',
      face: true,
      faces: faces,
      fps: fps,
      calibrated: base != null,
      calibrating: _calib != null,
      gazeH: _r3(_clamp(gazeH)),
      gazeV: _r3(_clamp(gazeV)),
      headYaw: _r3(_clamp(yaw)),
      headPitch: _r3(_clamp(pitch)),
      eyesOpen: _r3(m.open),
    );
  }
}

class Pt {
  const Pt(this.x, this.y);
  final double x, y;
}

/// Raw measurements of one face: iris position (h, v), eye opening, head turn and tilt.
class Raw {
  const Raw({required this.h, required this.v, required this.open, required this.yaw, required this.pitch});
  final double h, v, open, yaw, pitch;
}

class _Calib {
  _Calib(this.until);
  final double until;
  final rows = <Raw>[];
}
